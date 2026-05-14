"""
stt.py — MAX v4.2
Speech-to-Text via Groq Whisper.
Changes:
  - Added configurable `language` parameter (auto-detect by default)
  - Added `transcribe_wake_word()` — lightweight STT for wake word checking
  - Backward compatible: defaults still work as before
"""
import os
import asyncio
import logging
import tempfile
import subprocess
import base64
import binascii
from io import BytesIO
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


def _convert_webm_to_wav(webm_path: str) -> str:
    """Convert webm to wav for better Whisper compatibility."""
    wav_path = webm_path.replace(".webm", ".wav")
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", webm_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
            capture_output=True,
            text=True,
            timeout=15
        )
        if result.returncode == 0 and os.path.exists(wav_path) and os.path.getsize(wav_path) > 100:
            return wav_path
    except FileNotFoundError:
        pass  # ffmpeg not available, fall back to webm
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg conversion timed out")
    except Exception as e:
        logger.debug(f"ffmpeg conversion failed: {e}")
    return webm_path


async def transcribe_audio(
    audio_data: Union[bytes, str],
    model: str = "whisper-large-v3",
    language: str = ""  # Empty = auto-detect (best for mixed Hindi-English)
) -> str:
    """
    Transcribe audio bytes via Groq Whisper.
    
    Args:
        audio_data: Raw bytes or base64-encoded audio
        model: Whisper model to use
        language: Language code (e.g., "hi", "en", ""). 
                  Empty string enables auto-detection (best for Hinglish).
    """
    client = AsyncGroq(api_key=config.GROQ_API_KEY)
    tmp_path = None

    try:
        audio_bytes = _decode_audio_input(audio_data)
        if not audio_bytes:
            raise ValueError("Empty audio payload")

        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        # Try converting to wav for better compatibility
        file_to_transcribe = _convert_webm_to_wav(tmp_path)

        with open(file_to_transcribe, "rb") as f:
            audio_bytes = f.read()

        kwargs = {
            "file": ("audio.wav", audio_bytes, "audio/wav"),
            "model": model,
            "response_format": "text",
        }
        
        # Only pass language if explicitly specified
        if language:
            kwargs["language"] = language

        resp = await client.audio.transcriptions.create(**kwargs)
        
        # Cleanup temp files
        if file_to_transcribe != tmp_path and os.path.exists(file_to_transcribe):
            try:
                os.unlink(file_to_transcribe)
            except Exception as e:
                logger.debug(f"Temp cleanup failed (wav): {e}")

        return resp.text.strip() if hasattr(resp, 'text') else str(resp).strip()

    except Exception as e:
        logger.error(f"STT failed: {e}")
        return f"Sun nahi paya, dobara bol."
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception as e:
                logger.debug(f"Temp cleanup failed (webm): {e}")


async def transcribe_file(
    audio_path: str,
    model: str = "whisper-large-v3",
    language: str = ""
) -> str:
    """Transcribe an existing audio file."""
    client = AsyncGroq(api_key=config.GROQ_API_KEY)
    try:
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        kwargs = {
            "file": ("audio.wav", audio_bytes, "audio/wav"),
            "model": model,
            "response_format": "text",
        }
        if language:
            kwargs["language"] = language

        resp = await client.audio.transcriptions.create(**kwargs)
        return resp.text.strip() if hasattr(resp, 'text') else str(resp).strip()
    except Exception as e:
        logger.error(f"STT file failed: {e}")
        return "File transcribe nahi ho payi."


async def transcribe_wake_word(
    audio_data: Union[bytes, str],
    model: str = "whisper-large-v3"
) -> str:
    """
    Lightweight STT specifically for wake word detection.
    Uses auto language detection and short timeout.
    """
    try:
        return await asyncio.wait_for(
            transcribe_audio(audio_data, model=model, language=""),
            timeout=8.0
        )
    except asyncio.TimeoutError:
        logger.warning("Wake word STT timed out")
        return ""
    except Exception as e:
        logger.error(f"Wake word STT failed: {e}")
        return ""
