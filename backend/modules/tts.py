# Path: backend/modules/tts.py
# Use: Converts text responses into spoken voice output.
"""
tts.py — MAX v4.2
Text-to-Speech via Edge-TTS (Strictly English).
Added: Retry logic, better error handling, fallback mechanism.
"""
import os
import asyncio
import logging
import tempfile
from pathlib import Path
from config import config

logger = logging.getLogger("MAX.TTS")


async def generate_tts(text: str, voice: str = "", output_path: str = "") -> str:
    """Generate TTS audio with retry logic."""
    if not text or not text.strip():
        logger.warning("TTS called with empty text, skipping.")
        return ""

    try:
        import edge_tts
    except ImportError:
        logger.error("edge_tts not installed! Run: pip install edge-tts")
        return ""

    if not voice:
        voice = config.TTS_VOICE

    if not output_path:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        output_path = tmp.name
        tmp.close()

    # Retry up to 2 times on failure
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            tts = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=config.TTS_RATE_EN,
                pitch=config.TTS_PITCH_EN,
            )
            await tts.save(output_path)

            # Verify the file was actually created and has content
            if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                logger.info(f"TTS generated successfully: {os.path.getsize(output_path)} bytes")
                return output_path
            else:
                logger.warning(f"TTS file empty or missing (attempt {attempt + 1})")
                if attempt < max_retries:
                    await asyncio.sleep(0.5)
                    continue
                return ""

        except Exception as e:
            logger.error(f"TTS generation failed (attempt {attempt + 1}/{max_retries + 1}): {e}")
            if attempt < max_retries:
                await asyncio.sleep(0.5)
                continue
            # Final attempt failed — try fallback voice
            try:
                logger.info("Trying fallback voice: en-US-AriaNeural")
                fallback_tts = edge_tts.Communicate(
                    text=text,
                    voice="en-US-AriaNeural",
                    rate="+10%",
                    pitch="+0Hz",
                )
                await fallback_tts.save(output_path)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                    logger.info("TTS fallback voice succeeded")
                    return output_path
            except Exception as fallback_err:
                logger.error(f"TTS fallback also failed: {fallback_err}")
            return ""

    return ""


async def speak_text(text: str) -> bool:
    """Convenience: generate TTS and return path."""
    path = await generate_tts(text)
    return bool(path)