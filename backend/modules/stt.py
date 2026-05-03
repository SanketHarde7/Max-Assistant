"""
Speech-to-Text (STT) Module
Transcribes audio bytes using Groq Whisper API.
Independent, async, and handles audio format conversion gracefully.
"""
import io
import logging
import traceback
from groq import AsyncGroq
from config import config

logger = logging.getLogger(__name__)

# Lazy initialization: create client on first use
_groq_client = None


def get_groq_client():
    """Get or create Groq async client with error handling."""
    global _groq_client
    if _groq_client is None:
        try:
            _groq_client = AsyncGroq(api_key=config.GROQ_API_KEY)
            logger.info("✅ Groq STT client initialized")
        except TypeError as e:
            if "proxies" in str(e):
                logger.error("❌ httpx/groq version mismatch. Run: pip install groq httpx --upgrade")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to initialize Groq client: {e}")
            raise
    return _groq_client


async def transcribe_audio(audio_bytes: bytes, retries: int = 2) -> str:
    """
    Converts audio bytes to text using Groq Whisper.
    
    Args:
        audio_bytes: Raw audio data (WebM/MP3/WAV supported by Whisper)
        retries: Number of retry attempts for transient failures
        
    Returns:
        Transcribed text string. Empty string if silence/failure.
    """
    last_error = None
    
    for attempt in range(retries + 1):
        try:
            client = get_groq_client()
            
            # Whisper expects a file-like object
            file_obj = io.BytesIO(audio_bytes)
            file_obj.name = "audio.webm"
            
            response = await client.audio.transcriptions.create(
                model=config.WHISPER_MODEL,
                file=file_obj,
                language="en",  # Auto-detects (works for Hinglish too)
                temperature=0.0,                    
                response_format="text"
            )
            
            text = response.strip() if response else ""
            if not text:
                logger.warning("STT returned empty string. Likely silence.")
            else:
                logger.info(f"STT transcribed: '{text[:80]}...'")
            return text
            
        except Exception as e:
            last_error = e
            if attempt < retries:
                logger.warning(f"STT attempt {attempt + 1} failed, retrying: {e}")
                continue
            logger.error(f"STT Transcription failed after {retries + 1} attempts: {e}")
            logger.error(traceback.format_exc())
    
    return ""