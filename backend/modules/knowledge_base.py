"""
knowledge_base.py — MAX v4.2
Local RAG system using ChromaDB + sentence-transformers.

Architecture:
  .md files → chunked by header → embedded locally → stored in ChromaDB (persistent)
  User query → embed query → cosine similarity search → top-k chunks → inject into LLM context

Zero cost:
  - ChromaDB: local persistent DB (no cloud)
  - Embeddings: all-MiniLM-L6-v2 via sentence-transformers (~90MB, downloads once)

Install:
  pip install chromadb sentence-transformers

Usage:
  - Drop .md files in backend/knowledge/ folder
  - Say "knowledge base rebuild karo" OR auto-indexed on startup
  - MAX automatically injects relevant chunks when answering questions
"""
import re
import json
import logging
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("MAX.KNOWLEDGE")

# ─── folder name inside BACKEND_DIR ───
KNOWLEDGE_FOLDER = "knowledge"

# ─── Chunking config ───
MAX_CHUNK_SIZE   = 700   # chars per chunk — fits well in context
MIN_CHUNK_SIZE   = 80    # skip tiny fragments
OVERLAP_LINES    = 2     # lines of overlap between chunks


# ══════════════════════════════════════════════════
# Markdown → Chunks
# ══════════════════════════════════════════════════

def _split_markdown(text: str, source_name: str) -> List[Dict]:
    """
    Split a markdown document into semantic chunks.

    Strategy:
      1. Split on level 1-3 headers (# / ## / ###)
      2. If a section is still too long, split on double-newlines (paragraphs)
      3. Attach header and source metadata to every chunk

    Returns list of dicts: {id, text, source, header}
    """
    chunks: List[Dict] = []

    # Split at header boundaries — keep the header line with its section
    raw_sections = re.split(r'(?=\n#{1,3} )', "\n" + text)

    for sec_idx, section in enumerate(raw_sections):
        section = section.strip()
        if len(section) < MIN_CHUNK_SIZE:
            continue

        # Extract header label for metadata
        header_match = re.match(r'^(#{1,3})\s+(.+)', section)
        header = header_match.group(2).strip() if header_match else "General"

        if len(section) <= MAX_CHUNK_SIZE:
            chunks.append(_make_chunk(section, source_name, header, sec_idx, 0))
        else:
            # Split long sections into paragraph sub-chunks
            paragraphs = re.split(r'\n{2,}', section)
            current, sub_idx = "", 0
            carry_lines: List[str] = []    # overlap from previous para

            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                # Add overlap from previous chunk
                candidate = ("\n".join(carry_lines) + "\n" + para).strip() if carry_lines else para

                if len(current) + len(candidate) + 2 > MAX_CHUNK_SIZE and current:
                    chunks.append(_make_chunk(current, source_name, header, sec_idx, sub_idx))
                    sub_idx += 1
                    # Keep last OVERLAP_LINES as carry for next chunk
                    carry_lines = current.split("\n")[-OVERLAP_LINES:]
                    current = candidate
                else:
                    current = (current + "\n\n" + candidate).strip() if current else candidate

            if current and len(current) >= MIN_CHUNK_SIZE:
                chunks.append(_make_chunk(current, source_name, header, sec_idx, sub_idx))

    return chunks


def _make_chunk(text: str, source: str, header: str, sec: int, sub: int) -> Dict:
    # Use source + positions as stable ID (no UUID needed)
    chunk_id = f"{source}__{sec}__{sub}".replace(" ", "_").replace("/", "_")
    return {
        "id":     chunk_id,
        "text":   text.strip(),
        "source": source,
        "header": header,
    }


# ══════════════════════════════════════════════════
# KnowledgeBase class
# ══════════════════════════════════════════════════

class KnowledgeBase:
    """
    Persistent local vector store for MAX's knowledge documents.

    Lifecycle:
      1. __init__  — dirs created, ChromaDB client lazy-initialized
      2. build_index()  — scan .md files, embed, store in ChromaDB
      3. query(text)  — embed query, fetch top-k, return context string
    """

    def __init__(self, config):
        self.config        = config
        self.knowledge_dir = Path(config.BACKEND_DIR) / KNOWLEDGE_FOLDER
        self.chroma_dir    = Path(config.DATA_DIR)    / "chroma"
        self._client       = None
        self._collection   = None
        self._lock         = threading.Lock()
        self._ready        = False

        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)

    # ── internal: lazy ChromaDB init ──────────────────────

    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            # DefaultEmbeddingFunction uses all-MiniLM-L6-v2 (downloads ~90MB once)
            ef = embedding_functions.DefaultEmbeddingFunction()

            self._client     = chromadb.PersistentClient(path=str(self.chroma_dir))
            self._collection = self._client.get_or_create_collection(
                name="max_knowledge",
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
            self._ready = True
            logger.info(f"ChromaDB ready — {self._collection.count()} chunks stored")
            return self._collection

        except ImportError:
            logger.warning(
                "ChromaDB not installed. "
                "Run: pip install chromadb sentence-transformers"
            )
            return None
        except Exception as e:
            logger.error(f"ChromaDB init failed: {e}")
            return None

    # ── public: build full index ───────────────────────────

    def build_index(self) -> Dict:
        """
        Full scan of knowledge/ folder.
        Clears existing index and reindexes all .md files.
        Thread-safe.
        """
        with self._lock:
            collection = self._get_collection()
            if collection is None:
                return {"error": "ChromaDB not available. pip install chromadb sentence-transformers"}

            md_files = sorted(self.knowledge_dir.rglob("*.md"))
            if not md_files:
                return {
                    "files": 0, "chunks": 0,
                    "message": f"No .md files found in {self.knowledge_dir}. "
                               f"Drop markdown files there and rebuild."
                }

            # Clear all existing embeddings
            try:
                existing_ids = collection.get()["ids"]
                if existing_ids:
                    collection.delete(ids=existing_ids)
                    logger.info(f"Cleared {len(existing_ids)} old chunks")
            except Exception as e:
                logger.warning(f"Could not clear old index: {e}")

            total_chunks = 0
            indexed: List[str] = []
            errors: List[str]  = []

            for md_file in md_files:
                try:
                    text = md_file.read_text(encoding="utf-8", errors="replace").strip()
                    if not text:
                        continue

                    chunks = _split_markdown(text, md_file.name)
                    if not chunks:
                        continue

                    # ChromaDB batch add
                    collection.add(
                        ids=[c["id"] for c in chunks],
                        documents=[c["text"] for c in chunks],
                        metadatas=[{
                            "source":     c["source"],
                            "header":     c["header"],
                            "indexed_at": datetime.now().isoformat(),
                        } for c in chunks],
                    )
                    total_chunks += len(chunks)
                    indexed.append(f"{md_file.name} ({len(chunks)} chunks)")
                    logger.info(f"Indexed: {md_file.name} → {len(chunks)} chunks")

                except Exception as e:
                    errors.append(f"{md_file.name}: {e}")
                    logger.error(f"Failed to index {md_file.name}: {e}")

            result = {
                "files":   len(indexed),
                "chunks":  total_chunks,
                "indexed": indexed,
            }
            if errors:
                result["errors"] = errors
            return result

    # ── public: query ──────────────────────────────────────

    def query(
        self,
        question: str,
        top_k: int = 3,
        min_similarity: float = 0.30,
    ) -> Optional[str]:
        """
        Embed question, find top-k similar chunks, return formatted context.
        Returns None if nothing relevant found (so LLM skips KB injection).

        min_similarity: 0.0–1.0 (cosine). Lower = more permissive. 0.30 is a good default.
        """
        collection = self._get_collection()
        if collection is None:
            return None

        try:
            total = collection.count()
            if total == 0:
                return None

            results = collection.query(
                query_texts=[question],
                n_results=min(top_k, total),
                include=["documents", "metadatas", "distances"],
            )

            docs      = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas",  [[]])[0]
            distances = results.get("distances",  [[]])[0]

            if not docs:
                return None

            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity: 1 - d/2
            relevant = [
                (doc, meta, 1.0 - dist / 2.0)
                for doc, meta, dist in zip(docs, metadatas, distances)
                if 1.0 - dist / 2.0 >= min_similarity
            ]

            if not relevant:
                logger.debug(f"KB query: no results above similarity {min_similarity}")
                return None

            # Format context block for LLM injection
            lines = ["=== KNOWLEDGE BASE (answer using this if relevant) ==="]
            for doc, meta, sim in relevant:
                src    = meta.get("source", "?")
                header = meta.get("header", "")
                loc    = f"{src} › {header}" if header and header != "General" else src
                lines.append(f"[{loc}]")
                lines.append(doc[:600])  # cap per-chunk to avoid context overflow
                lines.append("")

            lines.append("=== END KNOWLEDGE BASE ===")

            logger.info(
                f"KB injected {len(relevant)} chunk(s) for: '{question[:60]}' "
                f"(similarities: {[f'{s:.2f}' for _,_,s in relevant]})"
            )
            return "\n".join(lines)

        except Exception as e:
            logger.error(f"KB query failed: {e}")
            return None

    # ── public: add single doc ─────────────────────────────

    def add_document(self, filename: str, content: str) -> str:
        """
        Add or update a single document without full rebuild.
        Useful for programmatic doc injection.
        """
        collection = self._get_collection()
        if collection is None:
            return "ChromaDB not available."

        with self._lock:
            try:
                # Remove old chunks for this file
                try:
                    old = collection.get(where={"source": filename})
                    if old["ids"]:
                        collection.delete(ids=old["ids"])
                except Exception:
                    pass

                chunks = _split_markdown(content, filename)
                if not chunks:
                    return "Document has no indexable content."

                collection.add(
                    ids=[c["id"] for c in chunks],
                    documents=[c["text"] for c in chunks],
                    metadatas=[{
                        "source":     c["source"],
                        "header":     c["header"],
                        "indexed_at": datetime.now().isoformat(),
                    } for c in chunks],
                )
                return f"'{filename}' indexed ({len(chunks)} chunks)."
            except Exception as e:
                return f"Failed to add '{filename}': {e}"

    # ── public: stats + listing ────────────────────────────

    def get_stats(self) -> Dict:
        collection = self._get_collection()
        md_files   = list(self.knowledge_dir.rglob("*.md"))
        if collection is None:
            return {
                "ready": False,
                "md_files": len(md_files),
                "error": "ChromaDB not installed",
            }
        try:
            return {
                "ready":       True,
                "chunks":      collection.count(),
                "md_files":    len(md_files),
                "kb_dir":      str(self.knowledge_dir),
                "chroma_dir":  str(self.chroma_dir),
            }
        except Exception as e:
            return {"ready": False, "error": str(e)}

    def list_documents(self) -> str:
        md_files = sorted(self.knowledge_dir.rglob("*.md"))
        stats    = self.get_stats()

        if not md_files:
            return (
                f"Knowledge base is empty.\n"
                f"Drop .md files in: {self.knowledge_dir}\n"
                f"Then say 'rebuild knowledge base'."
            )

        lines = [f"Knowledge base — {len(md_files)} file(s):"]
        for f in md_files:
            kb  = f.stat().st_size
            mod = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")
            lines.append(f"  • {f.name}  ({kb:,} bytes, modified {mod})")

        if stats.get("ready"):
            lines.append(f"\nTotal indexed chunks : {stats['chunks']}")
            lines.append(f"ChromaDB path        : {stats['chroma_dir']}")
        else:
            lines.append(f"\nNote: {stats.get('error', 'ChromaDB unavailable')}")

        return "\n".join(lines)


# ══════════════════════════════════════════════════
# Singleton + startup helper
# ══════════════════════════════════════════════════

_kb: Optional[KnowledgeBase] = None


def get_knowledge_base(config) -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase(config)
    return _kb


def auto_index_on_startup(config):
    """
    Call once at server startup in a daemon thread.
    Only rebuilds if .md files exist.
    """
    def _run():
        try:
            kb = get_knowledge_base(config)
            md_files = list(kb.knowledge_dir.rglob("*.md"))
            if not md_files:
                logger.info("KB: no .md files to index — skipping.")
                return
            result = kb.build_index()
            logger.info(f"KB startup index: {result}")
        except Exception as e:
            logger.warning(f"KB startup index failed: {e}")

    t = threading.Thread(target=_run, daemon=True, name="MAX-KB-Startup")
    t.start()
