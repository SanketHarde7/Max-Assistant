import asyncio
import logging
from config import config

logger = logging.getLogger("MAX.API_UTILS")

async def execute_with_retry(api_call_func, max_retries=3):
    """
    Execute an async API call with retry logic and API key rotation.
    The `api_call_func` should NOT cache the Groq client statically.
    It should instantiate the client (or get the active key) dynamically inside the function,
    so that if the key rotates, the next attempt uses the new key.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return await api_call_func()
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            
            # Rate limit - rotate key and retry immediately (no backoff needed)
            if "429" in str(e) or "rate limit" in error_str:
                if config.rotate_api_key():
                    logger.info(f"Rate limit hit. Rotated key. Retrying immediately (attempt {attempt+1}/{max_retries})")
                    continue
                else:
                    logger.warning("Rate limit hit, but no multiple API keys available to rotate.")
            
            # Server errors - retry with exponential backoff
            if any(code in str(e) for code in ["500", "502", "503", "504"]):
                wait_time = 2 ** attempt  # 1, 2, 4 seconds
                logger.warning(f"Server error {e}, retrying in {wait_time}s (attempt {attempt+1}/{max_retries})")
                await asyncio.sleep(wait_time)
                continue
            
            # Timeout - retry with exponential backoff
            if "timeout" in error_str:
                wait_time = 2 ** attempt
                logger.warning(f"Timeout, retrying in {wait_time}s (attempt {attempt+1}/{max_retries})")
                await asyncio.sleep(wait_time)
                continue
            
            # Other errors - don't retry, let it crash or be handled by the caller
            raise e
    
    raise last_error
