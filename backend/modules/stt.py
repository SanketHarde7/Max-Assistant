# Path: backend/modules/stt.py
# Use: Transcribes spoken audio input into text format.
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


async def _convert_webm_to_wav(webm_path: str) -> str:
    """Convert webm to wav asynchronously for better Whisper compatibility."""
    wav_path = webm_path.replace(".webm", ".wav")
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", webm_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            # Wait for process to complete with 15s timeout
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            if proc.returncode == 0 and os.path.exists(wav_path) and os.path.getsize(wav_path) > 100:
                return wav_path
        except asyncio.TimeoutError:
            logger.warning("ffmpeg conversion timed out")
            try:
                proc.kill()
            except Exception:
                pass
    except FileNotFoundError:
        pass  # ffmpeg not available, fall back to webm
    except Exception as e:
        logger.debug(f"ffmpeg conversion failed: {e}")
    return webm_path


async def transcribe_audio(
    audio_data: Union[bytes, str],
    model: str = "whisper-large-v3",
    language: str = ""  # Empty = auto-detect (best for mixed Hindi-English)
) -> str:
    """
    Transcribe audio bytes via Groq Whisper with retry on failure.
    Returns empty string on error (never returns fake transcript).
    """
    tmp_path = None
    wav_path = None

    try:
        audio_bytes = _decode_audio_input(audio_data)
        if not audio_bytes or len(audio_bytes) < 1000:
            logger.warning(f"Audio payload too small ({len(audio_bytes) if audio_bytes else 0} bytes), skipping STT")
            return ""

        is_wav = audio_bytes.startswith(b"RIFF")
        
        with tempfile.NamedTemporaryFile(suffix=".wav" if is_wav else ".webm", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        # For WAV files, skip FFmpeg conversion and transcribe directly.
        if is_wav:
            file_to_transcribe = tmp_path
        else:
            file_to_transcribe = await _convert_webm_to_wav(tmp_path)
            if file_to_transcribe != tmp_path:
                wav_path = file_to_transcribe

        with open(file_to_transcribe, "rb") as f:
            audio_bytes_read = f.read()

        kwargs = {
            "file": ("audio.wav", audio_bytes_read, "audio/wav"),
            "model": model,
            "response_format": "text",
            "prompt": "Hey Max, please listen carefully. Open chrome, pause the music, next song, system shutdown, volume up, search for latest news. How are you?",
        }

        # Only pass language if explicitly specified
        if language:
            kwargs["language"] = language

        # Retry once on failure
        max_retries = 2
        last_error = None
        for attempt in range(max_retries):
            try:
                client = AsyncGroq(api_key=config.GROQ_API_KEY)
                resp = await client.audio.transcriptions.create(**kwargs)
                result = resp.text.strip() if hasattr(resp, 'text') else str(resp).strip()
                if result:
                    return result
                return ""
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.warning(f"STT attempt {attempt + 1} failed: {e}, retrying...")
                    await asyncio.sleep(0.5)
                else:
                    logger.error(f"STT failed after {max_retries} attempts: {e}")

        return ""

    except Exception as e:
        logger.error(f"STT failed: {e}")
        return ""
    finally:
        # Clean up ALL temp files
        for path in [tmp_path, wav_path]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception as e:
                    logger.debug(f"Temp cleanup failed: {e}")


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
            "prompt": "Hey Max, please listen carefully. Open chrome, pause the music, next song, system shutdown, volume up, search for latest news. How are you?",
        }
        if language:
            kwargs["language"] = language

        resp = await client.audio.transcriptions.create(**kwargs)
        return resp.text.strip() if hasattr(resp, 'text') else str(resp).strip()
    except Exception as e:
        logger.error(f"STT file failed: {e}")
        return ""


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


import re

def is_hallucination(transcript: str) -> bool:
    if not transcript:
        return True
    
    # Strip common punctuation from ends
    text = transcript.lower().strip().rstrip(".।? ")
    
    hallucinations = {
        # Original English noise / Whisper artifacts
        "thank you", "thanks for watching", "thanks for watching.",
        "subtitles by amara.org", "subtitles by amara.org.", "um", "you", "go",
        "bye", "watching", "thanks", "please", "oh", "shirdi", "shirdi.",
        
        # Change 3: common single-letter/noise sounds
        "ah", "uh", "eh", "mm", "hmm", "moo", "baa", "ma", "na", "ha",
        
        # Change 3: common Whisper Hindi artifacts
        "हाँ", "हां", "अच्छा",
        
        # Change 3: generic audio words
        "music", "audio", "the music"
    }
    
    return text in hallucinations


def is_valid_transcript(transcript: str) -> bool:
    if not transcript or not transcript.strip():
        return False
        
    # Check if transcript is in the expanded hallucination list (Change 3)
    if is_hallucination(transcript):
        return False

    # Change 4: Single word filter
    # Extract alphanumeric words using regex
    words = re.findall(r'\b\w+\b', transcript.lower())
    if len(words) == 1:
        word = words[0]
        # Known commands list (pause, play, volume, next, haan, nahi, etc.)
        known_commands = {
            "pause", "play", "volume", "next", "haan", "nahi", "yes", "no",
            "stop", "cancel", "abort", "mute", "unmute", "kholo", "band",
            "open", "close", "max", "hello", "hi", "help",
            # App names (single-word voice commands)
            "browser", "chrome", "firefox", "edge", "spotify", "discord",
            "calculator", "notepad", "settings", "terminal", "explorer",
            "whatsapp", "telegram", "slack", "zoom", "teams",
            # Action words
            "search", "research", "weather", "screenshot", "timer", "record", "recording", "link",
            "calendar", "reminder", "shutdown", "restart", "lock",
            "brightness", "previous", "skip", "forward", "rewind",
            "exit", "quit", "time", "date", "clipboard",
        }
        if word not in known_commands:
            return False
            
    return True
