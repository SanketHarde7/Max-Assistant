"""
stt.py — MAX v4.0
Speech-to-Text via Groq Whisper.
"""
import os
import asyncio
import logging
import tempfile
import subprocess
import base64
import binascii
from typing import Union
from groq import AsyncGroq
from config import config

logger = logging.getLogger("MAX.STT")


def _decode_audio_input(audio_data: Union[bytes, str]) -> bytes:
    if isinstance(audio_data, bytes):
        return audio_data
    if not isinstance(audio_data, str):
        raise TypeError("audio_data must be bytes or base64 str")

    data = audio_data.strip()
    if data.startswith("data:"):
        parts = data.split(",", 1)
        if len(parts) == 2:
            data = parts[1]

    try:
        return base64.b64decode(data, validate=True)
    except binascii.Error:
        return base64.b64decode(data)


async def transcribe_audio(audio_data: Union[bytes, str], model: str = "whisper-large-v3") -> str:
    """Transcribe audio bytes via Groq Whisper."""
    client = AsyncGroq(api_key=config.GROQ_API_KEY)

    tmp_path = None
    try:
        audio_bytes = _decode_audio_input(audio_data)
        if not audio_bytes:
            raise ValueError("Empty audio payload")

        # Write audio bytes to a temp file for transcription
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(audio_bytes)
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
        return f"Sun nahi paya boss, dobara bol."
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
        return "File transcribe nahi ho payi boss."
