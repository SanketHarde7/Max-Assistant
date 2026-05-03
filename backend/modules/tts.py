"""
Text-to-Speech (TTS) Module
Generates MP3 audio using Microsoft Edge-TTS.
Returns raw bytes for streaming/playback.
"""
import io
import re
import edge_tts
import logging
import traceback
from config import config

logger = logging.getLogger(__name__)


def _fix_rate(rate: str) -> str:
    """Ensure rate is in edge-tts relative format like '+50%' or '-10%'."""
    rate = rate.strip()
    # If it's just a number like '150%', convert to relative
    match = re.match(r'^(\d+)%$', rate)
    if match:
        val = int(match.group(1)) - 100
        return f"+{val}%" if val >= 0 else f"{val}%"
    # Already in +/-N% format
    if re.match(r'^[+-]\d+%$', rate):
        return rate
    return "+0%"


def _fix_pitch(pitch: str) -> str:
    """Ensure pitch is in edge-tts format like '+0Hz'."""
    pitch = pitch.strip()
    if re.match(r'^[+-]\d+Hz$', pitch):
        return pitch
    # Try to normalize
    match = re.match(r'^(\d+)Hz$', pitch)
    if match:
        return f"+{match.group(1)}Hz"
    return "+0Hz"


async def text_to_speech(text: str) -> bytes:
    """
    Converts text to speech audio bytes.
    
    Args:
        text: Plain text response to speak
        
    Returns:
        MP3 audio bytes. Empty bytes on failure.
    """
    try:
        if not text or not text.strip():
            logger.warning("TTS: Empty text provided")
            return b""
        
        rate = _fix_rate(config.TTS_RATE)
        pitch = _fix_pitch(config.TTS_PITCH)
        
        logger.info(f"TTS: voice={config.TTS_VOICE}, rate={rate}, pitch={pitch}")
        
        communicate = edge_tts.Communicate(
            text=text,
            voice=config.TTS_VOICE,
            rate=rate,
            pitch=pitch
        )
        
        # Stream audio into memory buffer
        audio_buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.write(chunk["data"])
                
        audio_buffer.seek(0)
        audio_data = audio_buffer.getvalue()
        
        if len(audio_data) == 0:
            logger.warning("TTS: Generated empty audio")
            
        return audio_data
        
    except Exception as e:
        logger.error(f"TTS Generation failed: {e}")
        logger.error(traceback.format_exc())
        return b""