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


class WebAutopilotEngine:
    def __init__(self, config, llm_client=None):
        self.config = config
        self.llm = llm_client
        self._clean_old_cache()

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

        tts_callback(f"Starting background research on your topic. Please continue your work.", None)
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

            # Calling safe sync route inside background threads smoothly
            target_url = self.resolve_accurate_url_sync(raw_query)

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
                    tts_callback(
                        "Boss, the website blocked my background script. Should I open it normally on your screen so you can bypass it?", 
                        {"status": "bot_detected", "url": target_url}
                    )
                    return

            paragraphs = driver.find_elements(By.TAG_NAME, "p")
            scraped_text = "\n".join([p.text for p in paragraphs[:8] if len(p.text.strip()) > 20])

            if len(scraped_text.strip()) < 50:
                scraped_text = driver.find_element(By.TAG_NAME, "body").text[:1200]

            driver.quit()

            word_count = len(scraped_text.split())
            if word_count > 100:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = re.sub(r'[^a-zA-Z0-9]', '_', raw_query)[:20]
                file_path = CACHE_DIR / f"Research_{safe_name}_{ts}.txt"
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"=== MAX AGENTIC RESEARCH: {raw_query.upper()} ===\n")
                    f.write(f"Source URL: {target_url}\n")
                    f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                    f.write("="*50 + "\n\n")
                    f.write(scraped_text)

                tts_callback(
                    "Boss, information is stored in a file. Would you like me to open it?",
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