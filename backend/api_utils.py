# Path: backend/api_utils.py
# Use: Smart Groq API key pool — rate-limit aware key selection, cooldowns, retry & caching.
"""
api_utils.py — MAX v6.0 (Smart Rate-Limit Manager)

Manages multiple free-tier Groq API keys intelligently:
- Per-key sliding-window RPM tracking → least-loaded key is selected for EVERY request
  (instead of the old rotate-only-after-429 behaviour).
- Per-key cooldown on 429 — parses Groq's \"try again in Xs\" / Retry-After hints.
- Global concurrency semaphore so rapid voice commands never burst-hit the API.
- Exponential backoff with jitter for transient 5xx / timeout errors.
- Short-TTL response cache to eliminate duplicate requests (e.g. double STT triggers).
"""

import asyncio
import contextvars
import hashlib
import logging
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional

from config import config

logger = logging.getLogger("MAX.API_UTILS")

# Tracks which key the current asyncio task is using, so the retry logic
# knows exactly which key to put on cooldown when a 429 arrives.
_leased_key: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "leased_key", default=None
)


def _parse_retry_after(error_text: str) -> Optional[float]:
    """Extract the wait time from a Groq 429 error message, if present.

    Handles formats like:
      - \"Please try again in 7.66s\"
      - \"Please try again in 2m59.56s\"
      - \"retry-after: 12\"
    """
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", error_text, re.IGNORECASE)
    if m:
        minutes = int(m.group(1)) if m.group(1) else 0
        try:
            return minutes * 60 + float(m.group(2))
        except ValueError:
            pass
    m = re.search(r"retry[-_ ]after[\"':\s]+([\d.]+)", error_text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def make_cache_key(*parts: str) -> str:
    """Stable cache key from arbitrary string parts."""
    joined = "||".join(p or "" for p in parts)
    return hashlib.sha1(joined.encode("utf-8", errors="ignore")).hexdigest()


class TTLCache:
    """Tiny in-memory cache with per-entry expiry. Dedupes identical LLM calls."""

    def __init__(self, ttl: float = 15.0, max_size: int = 256) -> None:
        self.ttl = ttl
        self.max_size = max_size
        self._store: Dict[str, tuple] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if not item:
            return None
        value, expires_at = item
        if time.monotonic() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if len(self._store) >= self.max_size:
            oldest = min(self._store, key=lambda k: self._store[k][1])
            self._store.pop(oldest, None)
        self._store[key] = (value, time.monotonic() + self.ttl)


@dataclass
class _KeyState:
    """Live usage stats for one API key."""

    key: str
    timestamps: Deque[float] = field(default_factory=deque)  # request times in window
    cooldown_until: float = 0.0
    total_requests: int = 0
    total_429s: int = 0

    def prune(self, window: float) -> None:
        cutoff = time.monotonic() - window
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.popleft()

    def used(self, window: float) -> int:
        self.prune(window)
        return len(self.timestamps)

    def available(self, rpm: int, window: float) -> bool:
        if time.monotonic() < self.cooldown_until:
            return False
        return self.used(window) < rpm


class GroqKeyPool:
    """Smart pool over all configured Groq API keys.

    Every request leases the key with the most remaining capacity in the
    current 60-second window. Keys that received a 429 are placed on a
    cooldown and skipped until it expires.
    """

    WINDOW: float = 60.0  # sliding-window size in seconds

    def __init__(self) -> None:
        self.rpm_per_key: int = int(getattr(config, "GROQ_RPM_PER_KEY", 28))
        max_concurrent: int = int(getattr(config, "GROQ_MAX_CONCURRENT", 4))
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()
        self._states: Dict[str, _KeyState] = {}
        self._refresh_keys()

    def _refresh_keys(self) -> None:
        for key in config.GROQ_API_KEYS:
            if key not in self._states:
                self._states[key] = _KeyState(key=key)

    async def lease_key(self) -> str:
        """Pick the least-loaded, non-cooling key. Waits briefly if all are saturated."""
        deadline = time.monotonic() + 25.0
        while True:
            async with self._lock:
                self._refresh_keys()
                if not self._states:
                    raise ValueError("No GROQ_API_KEY found. Check your .env file.")
                candidates = [
                    s for s in self._states.values()
                    if s.available(self.rpm_per_key, self.WINDOW)
                ]
                if candidates:
                    best = min(
                        candidates,
                        key=lambda s: (s.used(self.WINDOW), s.total_429s),
                    )
                    best.timestamps.append(time.monotonic())
                    best.total_requests += 1
                    _leased_key.set(best.key)
                    return best.key
                wait = self._next_free_in()
            if time.monotonic() + wait > deadline:
                raise RuntimeError(
                    "All Groq API keys are rate-limited right now. "
                    "Please wait a few seconds and try again."
                )
            logger.info(f"⏳ All keys busy/cooling — waiting {wait:.1f}s for capacity…")
            await asyncio.sleep(wait)

    def _next_free_in(self) -> float:
        """Seconds until the soonest key becomes usable again."""
        now = time.monotonic()
        waits = []
        for s in self._states.values():
            cooldown_wait = max(0.0, s.cooldown_until - now)
            s.prune(self.WINDOW)
            window_wait = 0.0
            if len(s.timestamps) >= self.rpm_per_key and s.timestamps:
                window_wait = max(0.0, s.timestamps[0] + self.WINDOW - now)
            waits.append(max(cooldown_wait, window_wait))
        return (min(waits) + 0.25) if waits else 1.0

    def report_rate_limit(self, key: Optional[str], retry_after: Optional[float]) -> None:
        """Put a key on cooldown after a 429 so other keys carry the load."""
        if not key or key not in self._states:
            return
        state = self._states[key]
        cooldown = retry_after if retry_after and retry_after > 0 else 20.0
        cooldown = min(cooldown, 120.0)  # never bench a key for more than 2 minutes
        state.cooldown_until = max(state.cooldown_until, time.monotonic() + cooldown)
        state.total_429s += 1
        idx = list(self._states).index(key) + 1
        logger.warning(
            f"🚦 Groq key #{idx} rate-limited → cooling for {cooldown:.1f}s "
            f"(429s so far: {state.total_429s})"
        )

    def stats(self) -> Dict[str, Dict[str, Any]]:
        """Usage snapshot — handy for debugging/voice query."""
        now = time.monotonic()
        out: Dict[str, Dict[str, Any]] = {}
        for i, s in enumerate(self._states.values(), start=1):
            out[f"key_{i}"] = {
                "used_last_60s": s.used(self.WINDOW),
                "rpm_limit": self.rpm_per_key,
                "cooling_for_s": round(max(0.0, s.cooldown_until - now), 1),
                "total_requests": s.total_requests,
                "total_429s": s.total_429s,
            }
        return out


# ── Singletons ──
key_pool = GroqKeyPool()
response_cache = TTLCache(
    ttl=float(getattr(config, "GROQ_CACHE_TTL", 15.0)),
    max_size=256,
)


async def execute_with_retry(api_call_func, max_retries: int = 4):
    """Execute an async API call with smart retry logic.

    The `api_call_func` should instantiate its client dynamically inside the
    function (via llm.get_client) so each attempt leases a fresh key from the pool.

    Behaviour:
    - 429 / rate limit → cool down the offending key, retry immediately on another key.
    - 5xx / timeout / connection errors → exponential backoff with jitter.
    - Anything else → raise immediately for the caller to handle.
    - A global semaphore keeps concurrent bursts within safe limits.
    """
    last_error: Optional[Exception] = None
    async with key_pool.semaphore:
        for attempt in range(max_retries):
            try:
                return await api_call_func()
            except Exception as e:  # noqa: BLE001 — classified below
                last_error = e
                err_text = str(e)
                err_lower = err_text.lower()

                # Rate limit → bench this key, next attempt auto-selects another.
                if "429" in err_text or "rate limit" in err_lower:
                    key_pool.report_rate_limit(
                        _leased_key.get(), _parse_retry_after(err_text)
                    )
                    logger.info(
                        f"Rate limit hit — switching key "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    continue

                # Transient server / network issues → backoff with jitter.
                if (
                    any(code in err_text for code in ("500", "502", "503", "504"))
                    or "timeout" in err_lower
                    or "connection" in err_lower
                ):
                    wait_time = min(8.0, (2 ** attempt)) * (0.5 + random.random() * 0.5)
                    logger.warning(
                        f"Transient error ({e}) — retrying in {wait_time:.1f}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # Unknown error — don't retry blindly.
                raise

    raise last_error
