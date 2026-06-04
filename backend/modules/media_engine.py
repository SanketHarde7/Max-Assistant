"""
media_engine.py — MAX Smart Human-Like Media Engine v1.0
Intelligent YouTube search with AI intent parsing, semantic reranking,
caching, session tracking, and preference learning.
"""
import os
import json
import time
import asyncio
import re
import webbrowser
import logging
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus

from config import config
from modules.llm import get_client

logger = logging.getLogger("Jarvis")


def open_url_in_browser(url: str) -> None:
    logger.info(f"[MediaEngine] Opening URL: {url}")
    try:
        import platform
        import subprocess
        system = platform.system()
        if system == "Windows":
            os.startfile(url)
        elif system == "Darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
    except Exception as e:
        logger.error(f"[MediaEngine] Native browser open failed: {e}. Falling back to webbrowser.")
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e2:
            logger.error(f"[MediaEngine] Fallback webbrowser failed: {e2}")

# ── Storage paths ──
DATA_DIR = Path(config.DATA_DIR)
DATA_DIR.mkdir(parents=True, exist_ok=True)

PREF_FILE = DATA_DIR / "media_preferences.json"
HISTORY_FILE = DATA_DIR / "media_history.json"
SESSION_FILE = DATA_DIR / "current_session.json"
CACHE_FILE = DATA_DIR / "media_cache.json"

# ── Check yt-dlp availability ──
try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False
    logger.warning("yt-dlp not installed. Media engine will use HTML fallback.")


# ═══════════════════════════════════════
#  STORAGE HELPERS
# ═══════════════════════════════════════

class StorageManager:
    @staticmethod
    def load_json(filepath, default_data):
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return default_data.copy() if isinstance(default_data, dict) else default_data

    @staticmethod
    def save_json(filepath, data):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving {filepath}: {e}")


class MediaCache:
    def __init__(self):
        self.cache = StorageManager.load_json(CACHE_FILE, {"intent": {}, "search": {}})

    def get_intent(self, query):
        key = query.lower().strip()
        item = self.cache.get("intent", {}).get(key)
        if item and time.time() - item.get('timestamp', 0) < 3600 * 24:
            return item['data']
        return None

    def set_intent(self, query, data):
        key = query.lower().strip()
        if "intent" not in self.cache:
            self.cache["intent"] = {}
        self.cache["intent"][key] = {"data": data, "timestamp": time.time()}
        StorageManager.save_json(CACHE_FILE, self.cache)

    def get_search(self, query):
        key = query.lower().strip()
        item = self.cache.get("search", {}).get(key)
        if item and time.time() - item.get('timestamp', 0) < 3600 * 6:
            return item['data']
        return None

    def set_search(self, query, results):
        key = query.lower().strip()
        if "search" not in self.cache:
            self.cache["search"] = {}
        self.cache["search"][key] = {"data": results, "timestamp": time.time()}
        StorageManager.save_json(CACHE_FILE, self.cache)


class MediaSession:
    def __init__(self):
        self.session = StorageManager.load_json(SESSION_FILE, {})
        self.history = StorageManager.load_json(HISTORY_FILE, {
            "played_tracks": [], "skipped_tracks": [], "recent_queries": []
        })
        self.prefs = StorageManager.load_json(PREF_FILE, {
            "favorite_genres": [], "favorite_artists": [], "disliked_genres": []
        })

    def start_playback(self, query, track, candidates):
        """Record new playback session. Smart skip cooldown on previous track."""
        if self.session and "playback_started_at" in self.session:
            played_time = time.time() - self.session["playback_started_at"]
            prev_title = self.session.get("current_track", {}).get("title", "")
            if prev_title:
                if played_time > 30:
                    self.history.setdefault("played_tracks", []).append(prev_title)
                elif 3 < played_time <= 30:
                    self.history.setdefault("skipped_tracks", []).append(prev_title)

        # Serialize candidate tracks (only keep title + id to avoid bloat)
        safe_candidates = []
        for c in (candidates or [])[:10]:
            safe_candidates.append({
                "title": c.get("title", ""),
                "id": c.get("id", ""),
                "duration": c.get("duration", 0),
            })

        self.session = {
            "query": query,
            "current_track": {
                "title": track.get("title", ""),
                "id": track.get("id", ""),
                "duration": track.get("duration", 0),
            },
            "candidate_tracks": safe_candidates,
            "playback_started_at": time.time(),
        }
        self.history.setdefault("recent_queries", []).append(query)
        # Keep history bounded
        self.history["recent_queries"] = self.history["recent_queries"][-50:]
        self.history["played_tracks"] = self.history.get("played_tracks", [])[-100:]
        self.history["skipped_tracks"] = self.history.get("skipped_tracks", [])[-50:]

        StorageManager.save_json(SESSION_FILE, self.session)
        StorageManager.save_json(HISTORY_FILE, self.history)


# ═══════════════════════════════════════
#  MAIN ENGINE
# ═══════════════════════════════════════

class MediaEngine:
    def __init__(self):
        self.cache = MediaCache()
        self.session = MediaSession()

    # ── Intent Parsing ──

    def _is_simple_query(self, query):
        """Check if a query is simple enough to skip AI parsing."""
        q = query.lower().strip()
        words = q.split()
        # Very short queries are always simple
        if len(words) <= 4:
            return True
        # Queries with complex modifiers need AI
        complex_keywords = [
            "longer than", "shorter than", "more than", "less than",
            "hour", "minute", "mood", "vibe", "feeling", "energy",
            "coding", "gym", "workout", "study", "sleep", "relax",
            "boost", "focus", "chill", "late night"
        ]
        if any(k in q for k in complex_keywords):
            return False
        return True

    def _rule_based_parse(self, query):
        """Fast local parsing for simple queries."""
        q = query.lower()
        ptype = "song"
        if "playlist" in q:
            ptype = "playlist"
        elif "mix" in q:
            ptype = "mix"

        return {
            "search_query": query,
            "mood": None,
            "activity": None,
            "genre": None,
            "preferred_type": ptype,
            "min_duration_seconds": None,
            "max_duration_seconds": None,
            "allow_lyrics": True,
            "language": None,
            "confidence": 0.95,
        }

    async def _groq_intent_parse(self, query):
        """Use Groq LLM to extract structured media intent from complex queries."""
        client = get_client()
        prompt = f"""Extract media intent from this user request: "{query}"

Output ONLY valid JSON, no markdown, no explanation:
{{
  "search_query": "optimized youtube search string",
  "mood": "mood keyword or null",
  "activity": "activity keyword or null",
  "genre": "genre or null",
  "preferred_type": "song or playlist or mix",
  "min_duration_seconds": null,
  "max_duration_seconds": null,
  "allow_lyrics": true,
  "language": null,
  "confidence": 0.9
}}"""
        try:
            resp = await client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=200,
            )
            text = resp.choices[0].message.content.strip()
            # Strip markdown code fences
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            return json.loads(text.strip())
        except Exception as e:
            logger.error(f"[MediaEngine] Groq intent parsing failed: {e}")
            return self._rule_based_parse(query)

    async def parse_intent(self, query):
        """Parse user intent, using cache → rule-based → AI fallback."""
        cached = self.cache.get_intent(query)
        if cached:
            logger.info(f"[MediaEngine] Intent cache hit for: {query}")
            return cached

        if self._is_simple_query(query):
            logger.info(f"[MediaEngine] Simple query, rule-based parse: {query}")
            intent = self._rule_based_parse(query)
        else:
            logger.info(f"[MediaEngine] Complex query, using Groq AI parse: {query}")
            intent = await self._groq_intent_parse(query)

        self.cache.set_intent(query, intent)
        return intent

    # ── YouTube Search ──

    def _ytdlp_search(self, search_query, limit):
        """Search YouTube using yt-dlp. Returns list of video metadata dicts."""
        if not YTDLP_AVAILABLE:
            return []

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'extract_flat': False,      # MUST be False to get full metadata
            'default_search': 'auto',
            'noplaylist': True,
        }

        search_term = f"ytsearch{limit}:{search_query}"
        logger.info(f"[MediaEngine] yt-dlp searching: {search_term}")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                res = ydl.extract_info(search_term, download=False)
                if res and 'entries' in res:
                    entries = []
                    for e in res['entries']:
                        if e is None:
                            continue
                        entries.append({
                            'id': e.get('id', ''),
                            'title': e.get('title', ''),
                            'duration': e.get('duration', 0) or 0,
                            'view_count': e.get('view_count', 0) or 0,
                            'is_live': e.get('is_live', False),
                            'live_status': e.get('live_status', ''),
                            'channel': e.get('channel', ''),
                            'upload_date': e.get('upload_date', ''),
                        })
                    logger.info(f"[MediaEngine] yt-dlp returned {len(entries)} results")
                    return entries
        except Exception as e:
            logger.error(f"[MediaEngine] yt-dlp search failed: {e}")

        return []

    def _html_fallback_search(self, search_query, limit=5):
        """Fallback: scrape YouTube search HTML for video IDs when yt-dlp fails."""
        import urllib.request

        try:
            url = f"https://www.youtube.com/results?search_query={quote_plus(search_query)}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            video_ids = re.findall(r'"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', html)
            # Deduplicate while preserving order
            seen = set()
            unique_ids = []
            for vid in video_ids:
                if vid not in seen:
                    seen.add(vid)
                    unique_ids.append(vid)
                    if len(unique_ids) >= limit:
                        break

            results = []
            for vid in unique_ids:
                results.append({
                    'id': vid,
                    'title': f"YouTube Video ({vid})",
                    'duration': 0,
                    'view_count': 0,
                    'is_live': False,
                })

            logger.info(f"[MediaEngine] HTML fallback found {len(results)} video IDs")
            return results
        except Exception as e:
            logger.error(f"[MediaEngine] HTML fallback search failed: {e}")
            return []

    # ── Classification & Filtering ──

    def _classify_and_filter(self, results, intent):
        """Classify results and filter by duration/type constraints."""
        if not results:
            return []

        filtered = []
        for r in results:
            if not r or not r.get('id'):
                continue

            title = (r.get('title') or '').lower()
            duration = r.get('duration', 0) or 0
            is_live = r.get('is_live', False) or r.get('live_status') == 'is_live'

            # Classify content type
            c_type = "song"
            if any(kw in title for kw in ["playlist", "mix", "compilation", "mashup"]):
                c_type = "mix"
            if any(kw in title for kw in ["podcast", "interview", "talk"]):
                c_type = "podcast"
            if is_live:
                c_type = "live_stream"

            # Filter: reject live streams if user wants songs
            if is_live and intent.get('preferred_type') == "song":
                continue

            # Filter: reject podcasts if user wants songs
            if c_type == "podcast" and intent.get('preferred_type') in ("song", "mix"):
                continue

            # Duration filters (only apply if duration is known, i.e. > 0)
            min_d = intent.get('min_duration_seconds')
            max_d = intent.get('max_duration_seconds')
            if min_d and duration > 0 and duration < min_d:
                continue
            if max_d and duration > 0 and duration > max_d:
                continue

            r['c_type'] = c_type
            filtered.append(r)

        return filtered

    # ── Scoring ──

    def _local_score(self, candidates, intent):
        """Score candidates locally before sending top ones to LLM."""
        query_words = set(intent.get('search_query', '').lower().split())

        for c in candidates:
            score = 0.0
            title = (c.get('title') or '').lower()
            title_words = set(title.split())

            # Title word overlap (0 to 0.35)
            if query_words:
                overlap = len(query_words & title_words) / len(query_words)
                score += 0.35 * overlap

            # Popularity boost (0 to 0.20)
            views = c.get('view_count', 0) or 0
            if views > 10_000_000:
                score += 0.20
            elif views > 1_000_000:
                score += 0.15
            elif views > 100_000:
                score += 0.10
            elif views > 10_000:
                score += 0.05

            # Freshness boost (0 to 0.10)
            upload = c.get('upload_date', '')
            if upload:
                try:
                    days_old = (datetime.now() - datetime.strptime(upload, "%Y%m%d")).days
                    if days_old < 365:
                        score += 0.10
                    elif days_old < 365 * 3:
                        score += 0.05
                except Exception:
                    pass

            c['score'] = round(score, 4)

        candidates.sort(key=lambda x: x.get('score', 0), reverse=True)
        return candidates

    async def _semantic_rerank(self, candidates, intent):
        """Use Groq LLM to pick the best match from top 3 candidates."""
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        # Exact title match bypass
        query_lower = intent.get('search_query', '').lower()
        for c in candidates[:2]:
            if query_lower in (c.get('title') or '').lower():
                logger.info(f"[MediaEngine] Exact match found: {c.get('title')}")
                return c

        # If 3 or fewer candidates, just pick the top scored one
        if len(candidates) <= 3:
            return candidates[0]

        top_c = candidates[:3]
        client = get_client()
        options_text = "\n".join([
            f"[{i}] \"{c.get('title')}\" (Duration: {c.get('duration', 0)}s, Views: {c.get('view_count', 0)})"
            for i, c in enumerate(top_c)
        ])

        prompt = f"""Pick the BEST YouTube video for this request: "{intent.get('search_query', '')}"

Options:
{options_text}

Reply with ONLY the index number (0, 1, or 2). Nothing else."""

        try:
            resp = await client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=5,
            )
            match = re.search(r'\d+', resp.choices[0].message.content)
            if match:
                idx = int(match.group())
                if 0 <= idx < len(top_c):
                    return top_c[idx]
        except Exception as e:
            logger.warning(f"[MediaEngine] Semantic rerank failed: {e}")

        return top_c[0]

    # ── Main Playback Entry Point ──

    async def play_media(self, raw_query):
        """Main entry: parse intent → search → filter → score → play."""
        try:
            intent = await self.parse_intent(raw_query)
            logger.info(f"[MediaEngine] Intent: {json.dumps(intent, ensure_ascii=False)}")

            if intent.get('confidence', 1.0) < 0.4:
                return "Boss, I'm not sure what you want. Can you be more specific? (e.g., Gym playlist, Chill lofi, Arijit Singh)"

            search_query = intent.get('search_query', raw_query)

            # Apply user preferences for vague queries
            fav_genres = self.session.prefs.get("favorite_genres", [])
            if fav_genres and not self._is_simple_query(raw_query):
                search_query += f" {fav_genres[0]}"

            # Check search cache
            cached_results = self.cache.get_search(search_query)
            if cached_results:
                logger.info(f"[MediaEngine] Search cache hit: {len(cached_results)} results")
                results = cached_results
            else:
                # Dynamic candidate count
                limit = 5 if intent.get('confidence', 1.0) > 0.9 else 10
                
                # Primary: yt-dlp search
                results = await asyncio.to_thread(self._ytdlp_search, search_query, limit)

                # Fallback 1: HTML scrape
                if not results:
                    logger.warning("[MediaEngine] yt-dlp failed, trying HTML fallback")
                    results = await asyncio.to_thread(self._html_fallback_search, search_query, limit)

                if results:
                    self.cache.set_search(search_query, results)

            if not results:
                # Last resort: just open YouTube search in browser
                logger.warning("[MediaEngine] All searches failed, opening YouTube search page")
                open_url_in_browser(f"https://www.youtube.com/results?search_query={quote_plus(search_query)}")
                return f"Couldn't find exact results, so I opened YouTube search for '{raw_query}'."

            # Classify & filter
            filtered = self._classify_and_filter(results, intent)
            if not filtered:
                # Filters too strict — use unfiltered results
                filtered = [r for r in results if r and r.get('id')]

            if not filtered:
                open_url_in_browser(f"https://www.youtube.com/results?search_query={quote_plus(search_query)}")
                return f"Filters were too strict. Opened YouTube search for '{raw_query}'."

            # Score locally
            scored = self._local_score(filtered, intent)

            # Pick the best match
            if len(scored) > 3:
                best_match = await self._semantic_rerank(scored, intent)
            else:
                best_match = scored[0]

            if not best_match or not best_match.get('id'):
                open_url_in_browser(f"https://www.youtube.com/results?search_query={quote_plus(search_query)}")
                return f"Opened YouTube search for '{raw_query}'."

            # Build watch URL and play
            video_id = best_match['id']
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            logger.info(f"[MediaEngine] Playing: {best_match.get('title')} → {watch_url}")

            open_url_in_browser(watch_url)
            self.session.start_playback(raw_query, best_match, scored)

            title = best_match.get('title', raw_query)
            # Sanitize title: remove emojis/special chars that crash Windows encoding
            title = title.encode('ascii', errors='ignore').decode('ascii').strip()
            if not title:
                title = raw_query
            duration = best_match.get('duration', 0)
            dur_str = ""
            if duration:
                mins, secs = divmod(duration, 60)
                dur_str = f" ({int(mins)}:{int(secs):02d})"

            return f"Playing: {title}{dur_str}"

        except Exception as e:
            logger.error(f"[MediaEngine] play_media crashed: {e}", exc_info=True)
            # Ultimate fallback: open YouTube search
            try:
                open_url_in_browser(f"https://www.youtube.com/results?search_query={quote_plus(raw_query)}")
            except Exception:
                pass
            return f"Had an issue finding the best match, but I opened YouTube search for '{raw_query}'."


# ── Singleton instance ──
media_engine = MediaEngine()
