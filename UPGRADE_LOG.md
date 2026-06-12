# ⚡ MAX Upgrade Log

This file tracks every upgrade made to MAX — what changed, why it changed, the problem, the solution, and what output to expect after the change. Newest entries on top.

---

## Phase 1 — Smart Groq Rate-Limit Manager

**Date:** 2026-06-12 | **MR:** !8 | **Status:** ✅ Merged

### Files Changed
| File | Change |
|------|--------|
| `backend/api_utils.py` | Fully rewritten — new `GroqKeyPool`, `TTLCache`, smarter `execute_with_retry` |
| `backend/config.py` | Added 3 new settings: `GROQ_RPM_PER_KEY`, `GROQ_MAX_CONCURRENT`, `GROQ_CACHE_TTL` |
| `backend/modules/llm.py` | `get_client()` is now async + leases keys from pool; `get_response()` now has a dedupe cache; vision calls lease a fresh key per retry |
| `backend/modules/Intent_engine.py` | Intent classification LLM calls now lease keys from the pool |
| `backend/modules/stt.py` | Whisper transcription calls now lease keys from the pool |

### Problem
- MAX was hitting Groq free-tier **rate limits (RPM) very fast**, even with 4 API keys.
- Old logic was *reactive*: it used ONE key for everything and only rotated to the next key **after** a 429 error already happened. So one key got hammered while 3 keys sat idle.
- On 429 it retried **immediately** with the next key — during rapid voice commands this caused cascading 429s across all keys.
- Duplicate triggers (e.g. STT firing twice for the same sentence) burned extra API requests for the exact same answer.
- Rapid commands fired many simultaneous Groq calls at once (burst), tripping limits instantly.

### Solution
Built a proactive **smart key pool** (`GroqKeyPool` in `backend/api_utils.py`):
1. **Least-loaded key selection** — every single request picks the key with the most free capacity in the last 60 seconds (sliding window, default 28 requests/min per key as a safety margin under Groq's 30).
2. **Per-key cooldown on 429** — parses Groq's `"try again in 7.66s"` / `Retry-After` hint and benches ONLY that key for that duration (max 2 min). The other 3 keys keep serving traffic.
3. **Global concurrency semaphore** — max 4 Groq calls in flight at once across the whole app, so bursts get queued instead of slamming the API.
4. **Exponential backoff + jitter** for 5xx / timeout / connection errors (instead of hammering retries).
5. **15-second TTL response cache** — identical request within 15s returns the cached answer with ZERO API calls.
6. Wired the pool into **all** Groq call sites: main LLM, skill summaries, vision, intent classifier, and Whisper STT.

### Expected Output / How To Verify
- ✅ Rate-limit errors (`429`) should drop drastically — effectively you now have a smooth **~112 requests/min pool** instead of one overloaded key.
- ✅ Logs will show: `🚦 Groq key #2 rate-limited → cooling for 7.7s` when a key is benched (other keys keep working — no user-facing failure).
- ✅ Logs will show: `⚡ Cache hit — skipped one Groq request.` when a duplicate request is served from cache.
- ✅ If ALL 4 keys are genuinely saturated, MAX waits a few seconds for capacity instead of erroring instantly; only after ~25s does it say all keys are rate-limited.
- 🔧 Optional tuning in `.env` (defaults are already good):
  ```
  GROQ_RPM_PER_KEY=28      # requests per minute allowed per key
  GROQ_MAX_CONCURRENT=4    # max simultaneous Groq calls
  GROQ_CACHE_TTL=15        # seconds to cache identical responses
  ```
- ⚠️ Note: `GROQ_API_KEYS=key1,key2,key3,key4` in `.env` works exactly as before — nothing to change.
- 🧪 Debug helper: `from api_utils import key_pool; key_pool.stats()` shows live per-key usage (requests in last 60s, cooldowns, total 429s).

---

## Upcoming Phases (planned)

| Phase | Feature | Goal |
|-------|---------|------|
| 2 | **Agent Loop** (Plan → Act → Observe → Reflect) | Multi-step autonomous task execution with self-correction in `agent_core.py` |
| 3 | **Native Tool Calling** | Replace fragile `[SKILL:tag]` regex with Groq function calling (reliable multi-skill execution) |
| 4 | **Long-Term Memory** | Auto-extract facts/preferences from conversations into ChromaDB; recall over time |
| 5 | **Proactive Mode** | Background monitors (battery, reminders) + scheduled autonomous tasks that speak up on their own |
| 6 | **Skill Forge 2.0** | Agent writes, sandbox-tests and registers its own new skills automatically |
| 7 | **Web Autopilot 2.0** | Vision-based browsing fallback (screenshot → LLM decides click/type) when selectors fail |
| 8 | **Smart Gatekeeper** | 3-tier permissions: safe / voice-confirm / blocked for risky actions |
| 9 | **Voice Barge-in + Streaming TTS** | Sentence-by-sentence audio streaming + interrupt MAX mid-speech |
