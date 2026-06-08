# Path: backend/modules/ai_orchestrator/context_builder.py
# Use: Assembles prompts and context data for LLM.
# context_builder.py — Aggregates content from files, screen, clipboard, and text (Header Fix)
import os
import re
import logging
import pyperclip
from pathlib import Path
from typing import Dict, Any, Optional
from modules.ai_orchestrator.platform_config import PlatformInfo

logger = logging.getLogger("MAX.ORCHESTRATOR.CONTEXT")

# File size limits
MAX_PDF_PAGES = 50
MAX_IMAGE_SIZE_MB = 10
MAX_TEXT_FILE_SIZE_KB = 500


def extract_pdf_text(path: str) -> str:
    """Extract text from PDF with page limit."""
    try:
        from pdfminer.high_level import extract_text
        # Note: pdfminer doesn't have direct page limit, so we extract all then truncate
        text = extract_text(path)
        if len(text) > 500000:  # ~500KB of text is roughly 500 pages
            lines = text.split('\n')
            # Estimate: ~1000 chars per page
            chars_per_page_estimate = 1000
            keep_lines = int(MAX_PDF_PAGES * chars_per_page_estimate / max(len(lines), 1) * len(lines))
            text = '\n'.join(lines[:keep_lines]) + f"\n\n[Document truncated to approximately {MAX_PDF_PAGES} pages worth of content. Full document has more content.]"
        return text
    except ImportError:
        logger.error("pdfminer.six not installed. Run: pip install pdfminer.six")
        return "[Error: pdfminer.six not installed. Cannot extract PDF text.]"
    except Exception as e:
        logger.error(f"Failed to extract PDF text from {path}: {e}")
        return f"[Error: Failed to parse PDF: {e}]"


def extract_docx_text(path: str) -> str:
    """Extract text from DOCX file."""
    try:
        import docx
        doc = docx.Document(path)
        paragraphs = []
        for p in doc.paragraphs:
            if p.text.strip():
                paragraphs.append(p.text)
        text = "\n".join(paragraphs)
        if len(text) > 500000:
            text = text[:500000] + "\n\n[Document truncated due to length.]"
        return text
    except ImportError:
        logger.error("python-docx not installed. Run: pip install python-docx")
        return "[Error: python-docx not installed. Cannot extract DOCX text.]"
    except Exception as e:
        logger.error(f"Failed to extract DOCX text from {path}: {e}")
        return f"[Error: Failed to parse DOCX: {e}]"


def extract_txt_text(path: str) -> str:
    """Extract text from plain text file with size limit."""
    try:
        file_size_kb = os.path.getsize(path) / 1024
        if file_size_kb > MAX_TEXT_FILE_SIZE_KB:
            # Read partial
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read(MAX_TEXT_FILE_SIZE_KB * 1024)
            return text + f"\n\n[File truncated. Original size: {file_size_kb:.0f}KB, limit: {MAX_TEXT_FILE_SIZE_KB}KB]"
        else:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
    except Exception as e:
        logger.error(f"Failed to read text file {path}: {e}")
        return f"[Error: Failed to read file: {e}]"


async def extract_image_text(image_path: str) -> str:
    """Extract text from image using vision model."""
    try:
        # Check image size
        size_mb = os.path.getsize(image_path) / (1024 * 1024)
        if size_mb > MAX_IMAGE_SIZE_MB:
            # Resize image
            from PIL import Image
            with Image.open(image_path) as img:
                img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                resized_path = image_path + ".resized.jpg"
                img.save(resized_path, "JPEG", quality=75)
                image_path = resized_path
        
        from modules.llm import analyze_image_with_prompt
        return await analyze_image_with_prompt(
            image_path,
            "Extract all readable text, code, numbers, and structural content from this image. "
            "Output only the extracted text/code. Preserve formatting where possible."
        )
    except Exception as e:
        logger.error(f"Failed to run vision OCR on image {image_path}: {e}")
        return f"[Error: Failed to process image via Vision: {e}]"


def smart_chunk_text(text: str, chunk_size: int, overlap: int = 200) -> list:
    """
    Split text into chunks at word boundaries with overlap.
    Respects paragraph and sentence boundaries where possible.
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        if end >= len(text):
            chunks.append(text[start:])
            break
        
        # Try to find a good break point
        # Priority: paragraph > sentence > word
        search_text = text[start:end]
        
        # Look for paragraph break
        para_break = search_text.rfind('\n\n')
        if para_break > chunk_size * 0.5:
            end = start + para_break
        else:
            # Look for sentence break
            sentence_break = -1
            for delim in ['. ', '! ', '? ', '; ']:
                pos = search_text.rfind(delim)
                if pos > sentence_break and pos > chunk_size * 0.5:
                    sentence_break = pos + len(delim)
            
            if sentence_break > 0:
                end = start + sentence_break
            else:
                # Look for word boundary
                space_pos = search_text.rfind(' ')
                if space_pos > chunk_size * 0.7:
                    end = start + space_pos
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start with overlap
        start = end - overlap if end - overlap > start else end
    
    return chunks


class ContextBuilder:
    def __init__(self, config):
        self.config = config

    async def build_context(self, platform: PlatformInfo, direct_text: str, sources: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build context from multiple sources and chunk appropriately for the platform.
        """
        aggregated_parts = []
        image_to_upload: Optional[str] = None
        total_chars = 0

        # 1. Handle Clipboard Source
        if sources.get("clipboard"):
            try:
                clipboard_content = pyperclip.paste()
                if clipboard_content:
                    # Truncate very long clipboard content
                    if len(clipboard_content) > 50000:
                        clipboard_content = clipboard_content[:50000] + "\n\n[Clipboard content truncated due to length]"
                    aggregated_parts.append(
                        f"--- CLIPBOARD CONTENT ---\n{clipboard_content}\n--- END CLIPBOARD ---"
                    )
                    total_chars += len(clipboard_content)
            except Exception as e:
                logger.error(f"Failed to get clipboard content: {e}")

        # 2. Handle File Source
        file_path_str = sources.get("file")
        if file_path_str:
            path = Path(file_path_str).expanduser().resolve()
            if path.exists() and path.is_file():
                suffix = path.suffix.lower()
                file_size_kb = os.path.getsize(path) / 1024
                
                try:
                    if suffix in (".pdf",):
                        logger.info(f"Extracting PDF: {path.name} ({file_size_kb:.0f}KB)")
                        pdf_text = extract_pdf_text(str(path))
                        aggregated_parts.append(
                            f"--- FILE: {path.name} (PDF) ---\n{pdf_text}\n--- END FILE ---"
                        )
                        total_chars += len(pdf_text)
                        
                    elif suffix in (".docx", ".doc"):
                        logger.info(f"Extracting DOCX: {path.name} ({file_size_kb:.0f}KB)")
                        docx_text = extract_docx_text(str(path))
                        aggregated_parts.append(
                            f"--- FILE: {path.name} (DOCX) ---\n{docx_text}\n--- END FILE ---"
                        )
                        total_chars += len(docx_text)
                        
                    elif suffix in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
                        if platform.supports_image:
                            logger.info(f"Using image upload: {path.name}")
                            image_to_upload = str(path)
                        else:
                            logger.info(f"Platform doesn't support images, using OCR: {path.name}")
                            ocr_text = await extract_image_text(str(path))
                            aggregated_parts.append(
                                f"--- IMAGE OCR: {path.name} ---\n{ocr_text}\n--- END IMAGE ---"
                            )
                            total_chars += len(ocr_text)
                            
                    elif suffix in (".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".html", ".css", ".js", ".py", ".ts", ".tsx", ".jsx"):
                        logger.info(f"Reading text file: {path.name} ({file_size_kb:.0f}KB)")
                        content = extract_txt_text(str(path))
                        aggregated_parts.append(
                            f"--- FILE: {path.name} ---\n{content}\n--- END FILE ---"
                        )
                        total_chars += len(content)
                        
                    else:
                        # Try as text file for unknown extensions
                        logger.info(f"Attempting to read as text: {path.name}")
                        content = extract_txt_text(str(path))
                        aggregated_parts.append(
                            f"--- FILE: {path.name} ---\n{content}\n--- END FILE ---"
                        )
                        total_chars += len(content)
                        
                except Exception as e:
                    logger.error(f"Failed to process file {path}: {e}")
                    aggregated_parts.append(f"[Error: Could not process file {path.name}: {e}]")
            else:
                logger.warning(f"File not found: {file_path_str}")
                aggregated_parts.append(f"[Error: File not found: {file_path_str}]")

        # 3. Handle Screen Source (Screenshot)
        if sources.get("screen"):
            try:
                from PIL import ImageGrab
                ss_dir = Path(self.config.DATA_DIR) / "screenshots"
                ss_dir.mkdir(parents=True, exist_ok=True)
                path = ss_dir / "orchestrator_screen.jpg"
                
                img = ImageGrab.grab(all_screens=True).convert('RGB')
                img.thumbnail((1024, 1024))
                img.save(str(path), quality=70, optimize=True)
                
                if platform.supports_image:
                    logger.info("Using screen upload for image-capable platform")
                    image_to_upload = str(path)
                else:
                    logger.info("Running OCR on screenshot")
                    ocr_text = await extract_image_text(str(path))
                    aggregated_parts.append(
                        f"--- SCREEN CONTENT ---\n{ocr_text}\n--- END SCREEN ---"
                    )
                    total_chars += len(ocr_text)
            except Exception as e:
                logger.error(f"Failed to capture screen: {e}")
                aggregated_parts.append(f"[Error: Could not capture screen: {e}]")

        # Combine all context
        context_text = "\n\n".join(aggregated_parts)
        
        # ----------------------------------------------------------------------
        # 🟢 THE FIX: CONDITIONAL HEADER LOGIC 🟢
        # ----------------------------------------------------------------------
        if context_text:
            # If there are files/images attached, use the header to separate context from prompt
            final_prompt = f"{context_text}\n\n--- YOUR QUESTION/REQUEST ---\n{direct_text}"
            user_query_part = f"\n\n--- YOUR QUESTION/REQUEST ---\n{direct_text}"
        else:
            # If it's a simple query, send ONLY the clean text (No headers, no hidden newlines)
            final_prompt = direct_text
            user_query_part = f"\n\n{direct_text}"

        # Calculate effective limit with safety margin
        effective_limit = platform.char_limit - 1000  # 1000 char safety margin
        
        # Chunk intelligently if needed
        chunks = []
        if len(final_prompt) > effective_limit:
            logger.info(
                f"Prompt ({len(final_prompt)} chars) exceeds {platform.name} limit "
                f"({platform.char_limit}). Smart chunking..."
            )
            
            # Try to keep user query in every chunk
            available_for_context = effective_limit - len(user_query_part) - 100  # 100 for chunk header
            
            if available_for_context > 500 and context_text:
                # Split context into chunks
                context_chunks = smart_chunk_text(
                    context_text, 
                    available_for_context,
                    overlap=min(300, available_for_context // 4)
                )
                
                for i, ctx_chunk in enumerate(context_chunks):
                    if i < len(context_chunks) - 1:
                        chunk = (
                            f"[Part {i+1}/{len(context_chunks)} - Context Only]\n\n"
                            f"{ctx_chunk}\n\n"
                            f"[User request will follow in the next part]"
                        )
                    else:
                        chunk = (
                            f"[Final Part {i+1}/{len(context_chunks)} - Context + Request]\n\n"
                            f"{ctx_chunk}{user_query_part}"
                        )
                    chunks.append(chunk)
            else:
                # Not enough room for context, just chunk everything
                chunks = smart_chunk_text(final_prompt, effective_limit, overlap=200)
        else:
            chunks.append(final_prompt)

        return {
            "chunks": chunks,
            "image_path": image_to_upload,
            "is_chunked": len(chunks) > 1,
            "total_chars": sum(len(c) for c in chunks),
            "original_chars": len(final_prompt),
        }