# Path: backend/modules/knowledge_indexer.py
# Use: Indexes new files into the knowledge base.
"""
knowledge_indexer.py — MAX v4.0
Keyword indexer for local knowledge base markdown files.
"""
import json
import logging
import math
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("MAX.KNOWLEDGE")

_WORD_RE = re.compile(r"[a-zA-Z0-9]{3,}")


class KnowledgeIndexer:
    def __init__(self, config):
        self.config = config
        self.knowledge_dirs = self._unique_dirs(getattr(config, "KNOWLEDGE_DIRS", []))
        self.index_file = Path(getattr(config, "KNOWLEDGE_INDEX_FILE", config.DATA_DIR / "knowledge_index.json"))
        self.max_file_size_kb = getattr(config, "KNOWLEDGE_MAX_FILE_SIZE_KB", config.MAX_FILE_SIZE_KB)

        self._docs: List[dict] = []
        self._postings: Dict[str, List[List[int]]] = {}
        self._files_state: Dict[str, float] = {}
        self._built_at: float = 0.0

        self._load_index()

    def _unique_dirs(self, dirs: List[Path]) -> List[Path]:
        seen = set()
        unique = []
        for d in dirs:
            try:
                p = Path(d).expanduser()
                try:
                    p = p.resolve()
                except Exception:
                    pass
            except Exception:
                continue
            key = str(p).lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(p)
        return unique

    def _discover_files(self) -> List[Path]:
        files: List[Path] = []
        for d in self.knowledge_dirs:
            if not d.exists():
                continue
            try:
                for p in d.rglob("*.md"):
                    if p.is_file():
                        files.append(p)
            except Exception as e:
                logger.warning(f"Knowledge scan failed in {d}: {e}")
        return files

    def _read_text(self, path: Path) -> Optional[str]:
        try:
            size = path.stat().st_size
            max_bytes = self.max_file_size_kb * 1024
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read(max_bytes + 1)
            if size > max_bytes:
                text = text[:max_bytes]
            return text
        except Exception as e:
            logger.warning(f"Knowledge read failed: {path} ({e})")
            return None

    def _extract_title(self, path: Path, text: str) -> str:
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                if title:
                    return title
        return path.stem

    def _normalize_preview(self, text: str, max_len: int = 280) -> str:
        compact = " ".join(text.split())
        if len(compact) <= max_len:
            return compact
        return compact[:max_len].rstrip() + "..."

    def _tokenize(self, text: str) -> List[str]:
        return [m.group(0).lower() for m in _WORD_RE.finditer(text)]

    def _collect_state(self) -> Dict[str, float]:
        state: Dict[str, float] = {}
        for p in self._discover_files():
            try:
                state[str(p)] = p.stat().st_mtime
            except Exception:
                continue
        return state

    def _is_state_changed(self, current_state: Dict[str, float]) -> bool:
        if not self._files_state and not current_state:
            return False
        if len(self._files_state) != len(current_state):
            return True
        for path, mtime in current_state.items():
            if self._files_state.get(path) != mtime:
                return True
        return False

    def _load_index(self) -> None:
        if not self.index_file.exists():
            return
        try:
            data = json.loads(self.index_file.read_text(encoding="utf-8"))
            self._docs = data.get("docs", [])
            self._postings = data.get("postings", {})
            self._files_state = {k: float(v) for k, v in data.get("files_state", {}).items()}
            self._built_at = float(data.get("built_at", 0.0))
        except Exception as e:
            logger.warning(f"Knowledge index load failed: {e}")
            self._docs = []
            self._postings = {}
            self._files_state = {}
            self._built_at = 0.0

    def _save_index(self) -> None:
        try:
            payload = {
                "built_at": self._built_at,
                "docs": self._docs,
                "postings": self._postings,
                "files_state": self._files_state,
            }
            self.index_file.parent.mkdir(parents=True, exist_ok=True)
            self.index_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Knowledge index save failed: {e}")

    def build_index(self) -> int:
        files = self._discover_files()
        docs: List[dict] = []
        postings: Dict[str, List[List[int]]] = {}
        files_state: Dict[str, float] = {}

        for path in files:
            text = self._read_text(path)
            if not text:
                continue
            tokens = self._tokenize(text)
            if not tokens:
                continue

            term_freq: Dict[str, int] = {}
            for t in tokens:
                term_freq[t] = term_freq.get(t, 0) + 1

            doc_id = len(docs)
            title = self._extract_title(path, text)
            preview = self._normalize_preview(text)
            try:
                stat = path.stat()
                size = stat.st_size
                mtime = stat.st_mtime
            except Exception:
                size = 0
                mtime = 0.0

            docs.append({
                "id": doc_id,
                "path": str(path),
                "title": title,
                "preview": preview,
                "size": size,
                "mtime": mtime,
            })

            for term, count in term_freq.items():
                postings.setdefault(term, []).append([doc_id, count])

            if mtime:
                files_state[str(path)] = mtime

        self._docs = docs
        self._postings = postings
        self._files_state = files_state
        self._built_at = time.time()
        self._save_index()
        return len(self._docs)

    def refresh_if_needed(self) -> int:
        current_state = self._collect_state()
        if self._is_state_changed(current_state):
            return self.build_index()
        return len(self._docs)

    def search(self, query: str, limit: int = 5) -> str:
        q = (query or "").strip()
        if not q:
            return "Provide a query to search the knowledge base."

        self.refresh_if_needed()
        if not self._docs:
            return "Knowledge base is empty. Add .md files to your knowledge folder."

        tokens = self._tokenize(q)
        if not tokens:
            return "Query is too short. Use at least one meaningful word."

        scores: Dict[int, float] = {}
        total_docs = max(1, len(self._docs))

        for term in tokens:
            posting = self._postings.get(term)
            if not posting:
                continue
            df = len(posting)
            idf = math.log(1 + (total_docs / (1 + df)))
            for doc_id, tf in posting:
                scores[doc_id] = scores.get(doc_id, 0.0) + (tf * idf)

        if not scores:
            return "No matches found in the knowledge base."

        results = sorted(scores.items(), key=lambda x: x[1], reverse=True)[: max(1, limit)]
        lines = [f"Knowledge matches for: {q}"]
        for doc_id, _score in results:
            doc = self._docs[doc_id]
            rel_path = self._rel_path(doc.get("path", ""))
            title = doc.get("title") or Path(doc.get("path", "")).stem
            lines.append(f"- {title} ({rel_path})")
            preview = doc.get("preview", "").strip()
            if preview:
                lines.append(f"  {preview}")
        return "\n".join(lines)

    def _rel_path(self, path_str: str) -> str:
        try:
            p = Path(path_str)
            return p.relative_to(self.config.PROJECT_ROOT).as_posix()
        except Exception:
            try:
                return Path(path_str).as_posix()
            except Exception:
                return path_str


_indexer: Optional[KnowledgeIndexer] = None


def get_knowledge_indexer(config) -> KnowledgeIndexer:
    global _indexer
    if _indexer is None:
        _indexer = KnowledgeIndexer(config)
    return _indexer
