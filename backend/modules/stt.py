"""
stt.py — JARVIS v4.0
Speech-to-Text via Groq Whisper.
"""
import os
import asyncio
import logging
import tempfile
import subprocess
from groq import AsyncGroq
from config import config

logger = logging.getLogger("JARVIS.STT")


async def transcribe_audio(audio_data: bytes, model: str = "whisper-large-v3") -> str:
    """Transcribe audio bytes via Groq Whisper."""
    client = AsyncGroq(api_key=config.GROQ_API_KEY)

    tmp_path = None
    try:
        # Convert raw bytes to proper WAV if needed
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            tmp_path = f.name

        # Groq expects a file-like object
        with open(tmp_path, "rb") as audio_file:
            resp = await client.audio.transcriptions.create(
                file=audio_file,
                model=model,
                response_format="text",
                language="hi",  # Hindi-English mix
            )
        return resp.text.strip() if hasattr(resp, 'text') else str(resp).strip()

    except Exception as e:
        logger.error(f"STT failed: {e}")
        return f"Sun nahi paya bhai, dobara bol."
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def transcribe_file(audio_path: str, model: str = "whisper-large-v3") -> str:
    """Transcribe an existing audio file."""
    client = AsyncGroq(api_key=config.GROQ_API_KEY)
    try:
        with open(audio_path, "rb") as audio_file:
            resp = await client.audio.transcriptions.create(
                file=audio_file,
                model=model,
                response_format="text",
                language="hi",
            )
        return resp.text.strip() if hasattr(resp, 'text') else str(resp).strip()
    except Exception as e:
        logger.error(f"STT file failed: {e}")
        return "File transcribe nahi ho payi bhai."
