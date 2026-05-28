"""
web_autopilot.py — MAX v5.1 (Agentic Browsing & Thread-Safe Engine)
- Implements Headless & Invisible undetected-chromedriver loops.
- Handles Cloudflare auto-wait (up to 10 seconds).
- Incorporates 3-Layer accuracy (Safe Map, Sync Domain Corrector, Search Validation).
- Saves long research outputs to local file cache with non-blocking threading.
"""
import os
import re
import time
import json
import logging
import threading
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus
import httpx
from datetime import datetime

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

logger = logging.getLogger("MAX.WEB_AUTOPILOT")

CORE_DEVELOPER_MAP = {
    "vercel": "https://vercel.com",
    "github": "https://github.com",
    "google console": "https://console.cloud.google.com",
    "aws": "https://aws.amazon.com",
    "render": "https://render.com",
    "firebase": "https://firebase.google.com",
    "supabase": "https://supabase.com",
    "chatgpt": "https://chatgpt.com",
    "stackoverflow": "https://stackoverflow.com",
    "localhost": "http://localhost:3000"
}

CACHE_DIR = Path("./MAX_Research_Cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

LAST_BOT_BYPASS_URL = None

def clear_last_bot_bypass_url():
    global LAST_BOT_BYPASS_URL
    LAST_BOT_BYPASS_URL = None



class WebAutopilotEngine:
    def __init__(self, config, llm_client=None):
        self.config = config
        self.llm = llm_client
        self._clean_old_cache()

    def _format_research_with_llm(self, query: str, raw_text: str) -> str:
        """Use LLM to format raw scraped text into a well-structured research document."""
        try:
            from groq import Groq
            api_key = self.config.get_active_api_key()
            if not api_key:
                logger.warning("No API key for research formatting, using raw text")
                return raw_text

            client = Groq(api_key=api_key)
            prompt = f"""You are a research writer. Convert the following raw scraped web content into a comprehensive, well-structured research document about "{query}".

Rules:
- Write in a clear, natural, human-friendly tone — as if a knowledgeable friend is explaining
- Use proper HEADINGS, SECTIONS, and PARAGRAPHS for readability
- Include ALL key facts, data, explanations, and insights from the content
- Remove web artifacts (navigation links, ads, cookie notices, unrelated text)
- Organize information logically: Overview first, then details, then key takeaways
- Be comprehensive and detailed — do NOT skip information
- If the content is thin, expand with your own knowledge on the topic
- Write in English
- Do NOT use markdown code blocks or special formatting — plain text with clear section headers

Raw scraped content:
{raw_text[:5000]}

Write the formatted research document now:"""

            resp = client.chat.completions.create(
                model=self.config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=3000,
            )
            formatted = resp.choices[0].message.content.strip()
            if len(formatted) > 50:
                return formatted
            logger.warning("LLM returned too short formatted text, using raw")
            return raw_text
        except Exception as e:
            logger.warning(f"LLM research formatting failed, using raw text: {e}")
            return raw_text

    def _clean_old_cache(self):
        try:
            now = time.time()
            for f in CACHE_DIR.glob("*.*"):
                if now - f.stat().st_mtime > 48 * 3600:
                    f.unlink()
        except Exception as e:
            logger.warning(f"Cache cleanup failed: {e}")

    def resolve_accurate_url_sync(self, query: str) -> str:
        """Pure synchronous URL resolver. 100% immune to Asyncio loop crashes."""
        clean_query = query.strip().lower()

        # Layer 1: Core Map Check
        if clean_query in CORE_DEVELOPER_MAP:
            return CORE_DEVELOPER_MAP[clean_query]

        for key, url in CORE_DEVELOPER_MAP.items():
            if key in clean_query or clean_query in key:
                return url

        # Layer 3: Synchronous Search Engine Validation API
        try:
            encoded = quote_plus(query)
            url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1"
            # Using standard synchronous client to bypass thread/loop binding issues
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    abstract_url = data.get("AbstractURL", "")
                    if abstract_url:
                        return abstract_url
        except Exception as e:
            logger.warning(f"[Sync Layer 3] Search fallback validation failed: {e}")

        # Last resort cleaner
        fallback = query.replace(" ", "").lower()
        if not fallback.startswith(("http://", "https://")):
            fallback = "https://" + fallback + ".com"
        return fallback

    async def resolve_accurate_url(self, query: str) -> str:
        """Async version for standard asynchronous pipelines."""
        return self.resolve_accurate_url_sync(query)

    def run_background_research(self, raw_query: str, tts_callback):
        thread = threading.Thread(
            target=self._execute_selenium_research_loop, 
            args=(raw_query, tts_callback), 
            daemon=True
        )
        thread.start()

    def _execute_selenium_research_loop(self, raw_query: str, tts_callback):
        if not SELENIUM_AVAILABLE:
            tts_callback("Boss, undetected-chromedriver library is missing.", None)
            return

        # NOTE: Initial ack is already sent by _skill_research() return value.
        # Do NOT send another tts_callback here — it causes double-speak / voice bleed.
        driver = None
        try:
            options = uc.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--window-position=-32000,-32000")
            
            user_data = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
            if os.path.exists(user_data):
                options.add_argument(f"--user-data-dir={user_data}")
                options.add_argument("--profile-directory=Default")

            # Smart research URL resolution:
            # If the query looks like a URL → resolve it normally.
            # If it's a generic topic → use DuckDuckGo HTML search for broad results.
            clean_query = raw_query.strip()
            looks_like_url = any(clean_query.lower().startswith(p) for p in ("http://", "https://", "www.")) \
                             or ("." in clean_query and " " not in clean_query)

            if looks_like_url:
                target_url = self.resolve_accurate_url_sync(clean_query)
            else:
                # Generic topic → search engine page for richer content
                target_url = f"https://html.duckduckgo.com/html/?q={quote_plus(clean_query)}"

            driver = uc.Chrome(options=options, version_main=None)
            driver.get(target_url)

            time.sleep(3.0)
            page_title = driver.title.lower()
            
            if "just a moment" in page_title or "cloudflare" in page_title or "checking your browser" in page_title:
                for attempt in range(1, 6):
                    time.sleep(2.0)
                    updated_title = driver.title.lower()
                    if "just a moment" not in updated_title and "cloudflare" not in updated_title:
                        break
                else:
                    driver.quit()
                    global LAST_BOT_BYPASS_URL
                    LAST_BOT_BYPASS_URL = target_url
                    tts_callback(
                        "Boss, the website blocked my background script. Should I open it normally on your screen so you can bypass it?", 
                        {"status": "bot_detected", "url": target_url}
                    )
                    return

            # Deep scraping: paragraphs, articles, and list items for richer results
            paragraphs = driver.find_elements(By.TAG_NAME, "p")
            scraped_text = "\n".join([p.text for p in paragraphs[:20] if len(p.text.strip()) > 20])

            # Also scrape article and list item content for additional depth
            if len(scraped_text.strip()) < 200:
                for tag in ["article", "section", "li"]:
                    try:
                        elements = driver.find_elements(By.TAG_NAME, tag)
                        extra = "\n".join([el.text for el in elements[:15] if len(el.text.strip()) > 20])
                        scraped_text = (scraped_text + "\n" + extra).strip()
                        if len(scraped_text) > 500:
                            break
                    except Exception:
                        continue

            if len(scraped_text.strip()) < 50:
                scraped_text = driver.find_element(By.TAG_NAME, "body").text[:3000]

            driver.quit()

            word_count = len(scraped_text.split())
            if word_count > 100:
                # Format raw content into a proper research document via LLM
                formatted_text = self._format_research_with_llm(raw_query, scraped_text)

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = re.sub(r'[^a-zA-Z0-9]', '_', raw_query)[:20]
                file_path = CACHE_DIR / f"Research_{safe_name}_{ts}.txt"
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"{'='*60}\n")
                    f.write(f"  MAX RESEARCH REPORT: {raw_query.upper()}\n")
                    f.write(f"{'='*60}\n")
                    f.write(f"Source: {target_url}\n")
                    f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"{'='*60}\n\n")
                    f.write(formatted_text)

                tts_callback(
                    f"Research complete! I've created a detailed research file on {raw_query}. It's saved in your research cache folder.",
                    {"status": "file_saved", "file_path": str(file_path.absolute())}
                )
            else:
                tts_callback(f"Here is what I found: {scraped_text}", {"status": "direct_text"})

        except Exception as e:
            logger.error(f"Selenium Autopilot Loop exploded: {e}")
            if driver:
                try: driver.quit()
                except Exception: pass
            tts_callback("Sorry boss, I ran into an error while scraping the page.", None)