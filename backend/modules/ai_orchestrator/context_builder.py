# context_builder.py — Aggregates content from files, screen, clipboard, and text
import os
import logging
import pyperclip
from pathlib import Path
from typing import Dict, Any, Optional
from modules.ai_orchestrator.platform_config import PlatformInfo

logger = logging.getLogger("MAX.ORCHESTRATOR.CONTEXT")

def extract_pdf_text(path: str) -> str:
    try:
        from pdfminer.high_level import extract_text
        return extract_text(path)
    except Exception as e:
        logger.error(f"Failed to extract PDF text from {path}: {e}")
        return f"[Error: Failed to parse PDF: {e}]"

def extract_docx_text(path: str) -> str:
    try:
        import docx
        doc = docx.Document(path)
        return "\n".join([p.text for p in doc.paragraphs])
    except Exception as e:
        logger.error(f"Failed to extract DOCX text from {path}: {e}")
        return f"[Error: Failed to parse DOCX: {e}]"

async def extract_image_text(image_path: str) -> str:
    try:
        from modules.llm import analyze_image_with_prompt
        return await analyze_image_with_prompt(
            image_path,
            "Extract all readable text, code, numbers, and structural content from this image. Output only the extracted text/code."
        )
    except Exception as e:
        logger.error(f"Failed to run vision OCR on image {image_path}: {e}")
        return f"[Error: Failed to process image via Vision: {e}]"

class ContextBuilder:
    def __init__(self, config):
        self.config = config

    async def build_context(self, platform: PlatformInfo, direct_text: str, sources: Dict[str, Any]) -> Dict[str, Any]:
        """
        sources can be:
        - "clipboard": bool
        - "screen": bool
        - "file": str (filepath)
        """
        aggregated_parts = []
        image_to_upload: Optional[str] = None

        # 1. Handle Clipboard Source
        if sources.get("clipboard"):
            try:
                clipboard_content = pyperclip.paste()
                if clipboard_content:
                    aggregated_parts.append(f"--- START CLIPBOARD CONTENT ---\n{clipboard_content}\n--- END CLIPBOARD CONTENT ---")
            except Exception as e:
                logger.error(f"Failed to get clipboard content: {e}")

        # 2. Handle File Source
        file_path_str = sources.get("file")
        if file_path_str:
            path = Path(file_path_str).expanduser().resolve()
            if path.exists() and path.is_file():
                suffix = path.suffix.lower()
                if suffix in (".pdf",):
                    pdf_text = extract_pdf_text(str(path))
                    aggregated_parts.append(f"--- START FILE CONTENT ({path.name}) ---\n{pdf_text}\n--- END FILE CONTENT ---")
                elif suffix in (".docx", ".doc"):
                    docx_text = extract_docx_text(str(path))
                    aggregated_parts.append(f"--- START FILE CONTENT ({path.name}) ---\n{docx_text}\n--- END FILE CONTENT ---")
                elif suffix in (".png", ".jpg", ".jpeg", ".webp"):
                    if platform.supports_image:
                        image_to_upload = str(path)
                    else:
                        ocr_text = await extract_image_text(str(path))
                        aggregated_parts.append(f"--- START IMAGE OCR CONTENT ({path.name}) ---\n{ocr_text}\n--- END IMAGE OCR CONTENT ---")
                else:
                    # Treat as text file
                    try:
                        content = path.read_text(encoding="utf-8", errors="replace")
                        aggregated_parts.append(f"--- START FILE CONTENT ({path.name}) ---\n{content}\n--- END FILE CONTENT ---")
                    except Exception as e:
                        logger.error(f"Failed to read text file {path}: {e}")
            else:
                logger.warning(f"File {file_path_str} does not exist or is not a file.")

        # 3. Handle Screen Source (Screenshot)
        if sources.get("screen"):
            try:
                from PIL import ImageGrab
                ss_dir = Path(self.config.DATA_DIR) / "screenshots"
                ss_dir.mkdir(parents=True, exist_ok=True)
                path = ss_dir / "orchestrator_screen.jpg"
                
                # Capture screen
                img = ImageGrab.grab(all_screens=True).convert('RGB')
                img.thumbnail((1024, 1024))
                img.save(str(path), quality=70, optimize=True)
                
                if platform.supports_image:
                    image_to_upload = str(path)
                else:
                    ocr_text = await extract_image_text(str(path))
                    aggregated_parts.append(f"--- START SCREEN OCR CONTENT ---\n{ocr_text}\n--- END SCREEN OCR CONTENT ---")
            except Exception as e:
                logger.error(f"Failed to capture screen: {e}")

        # Combine text context
        context_text = "\n\n".join(aggregated_parts)
        
        # Build prompt
        final_prompt = ""
        if context_text:
            final_prompt += f"{context_text}\n\n"
        final_prompt += direct_text

        # limit prompt characters if it exceeds the limit
        chunks = []
        if len(final_prompt) > platform.char_limit:
            logger.warning(f"Prompt length ({len(final_prompt)}) exceeds platform {platform.name} limit ({platform.char_limit}). Chunking...")
            limit = platform.char_limit - 1000  # safety margin
            # simple split by length
            for i in range(0, len(final_prompt), limit):
                chunks.append(final_prompt[i:i+limit])
        else:
            chunks.append(final_prompt)

        return {
            "chunks": chunks,
            "image_path": image_to_upload,
            "is_chunked": len(chunks) > 1
        }
