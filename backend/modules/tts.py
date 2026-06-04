"""
tts.py — MAX v4.1
Text-to-Speech via Edge-TTS (Strictly English).
"""
import os
import asyncio
import logging
import tempfile
from pathlib import Path
from config import config

logger = logging.getLogger("MAX.TTS")


async def generate_tts(text: str, voice: str = "", output_path: str = "") -> str:
    """Generate TTS audio."""
    try:
        import edge_tts
    except ImportError:
        logger.warning("edge_tts not installed. 'pip install edge-tts' for TTS.")
        return ""

    if not voice:
        voice = config.TTS_VOICE

    if not output_path:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        output_path = tmp.name
        tmp.close()

    try:
        tts = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=config.TTS_RATE_EN,
            pitch=config.TTS_PITCH_EN,
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