"""
tts.py — MAX v4.1
Text-to-Speech via Edge-TTS with automatic Hindi/English voice switching.
"""
import os
import asyncio
import logging
import tempfile
from pathlib import Path
from config import config
from modules.language_detector import detect_language

logger = logging.getLogger("MAX.TTS")


async def generate_tts(text: str, voice: str = "", output_path: str = "") -> str:
    """Generate TTS audio. Auto-selects Hindi voice if text contains Hindi script."""
    try:
        import edge_tts
    except ImportError:
        logger.warning("edge_tts not installed. 'pip install edge-tts' for TTS.")
        return ""

    # Auto-detect language if no voice explicitly provided
    is_hindi_voice = False
    if not voice:
        lang = detect_language(text)
        if lang == "hi":
            voice = config.TTS_VOICE_HINDI
            is_hindi_voice = True
            logger.debug(f"Using Hindi voice: {voice}")
        else:
            voice = config.TTS_VOICE
            logger.debug(f"Using English voice: {voice}")
    else:
        lowered = voice.lower()
        is_hindi_voice = lowered.startswith("hi-") or voice == config.TTS_VOICE_HINDI

    if not output_path:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        output_path = tmp.name
        tmp.close()

    try:
        rate = config.TTS_RATE_HINDI if is_hindi_voice else config.TTS_RATE_EN
        pitch = config.TTS_PITCH_HINDI if is_hindi_voice else config.TTS_PITCH_EN
        tts = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            pitch=pitch,
        )
        await tts.save(output_path)
        return output_path
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        return ""


async def speak_text(text: str) -> bool:
    """Convenience: generate TTS and return path."""
    path = await generate_tts(text)
    return bool(path)