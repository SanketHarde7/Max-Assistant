"""
tts.py — MAX v4.0
Text-to-Speech via Edge-TTS (free, no API keys needed).
"""
import os
import asyncio
import logging
import tempfile
import subprocess
from pathlib import Path
from config import config

logger = logging.getLogger("MAX.TTS")


async def generate_tts(text: str, voice: str = "", output_path: str = "") -> str:
    """Generate TTS audio using Edge-TTS. Returns path to audio file."""
    try:
        import edge_tts
    except ImportError:
        logger.warning("edge_tts not installed. 'pip install edge-tts' for TTS.")
        return ""

    voice = voice or config.TTS_VOICE
    if not output_path:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        output_path = tmp.name
        tmp.close()

    try:
        tts = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=config.TTS_RATE,
            pitch=config.TTS_PITCH,
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
