# Path: backend/modules/web_autopilot.py
# Use: Automates web browsing, searches, and interactions.
# web_autopilot.py — MAX v5.2 (Agentic Browsing & Thread-Safe Engine)
# - Implements Headless & Invisible undetected-chromedriver loops.
# - Handles Cloudflare auto-wait (up to 10 seconds).
# - 3-Layer accuracy (Safe Map, Sync Domain Corrector, Search Validation).
# - Saves long research outputs to local file cache with non-blocking threading.
import os
import re
import time
import json
import logging
import threading
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse, parse_qs
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
    "gcp console": "https://console.cloud.google.com",
    "firebase console": "https://console.firebase.google.com",
    "aws": "https://aws.amazon.com",
    "aws console": "https://aws.amazon.com/console",
    "render": "https://render.com",
    "firebase": "https://firebase.google.com",
    "supabase": "https://supabase.com",
    "chatgpt": "https://chatgpt.com",
    "chatgpt.com": "https://chatgpt.com",
    "openai": "https://openai.com",
    "stackoverflow": "https://stackoverflow.com",
    "localhost": "http://localhost:3000",
    "localhost 3000": "http://localhost:3000",
    "localhost 5173": "http://localhost:5173",
    "localhost 8000": "http://localhost:8000",
    "localhost 8080": "http://localhost:8080",
    "claude": "https://claude.ai",
    "claude.ai": "https://claude.ai",
    "anthropic": "https://anthropic.com",
    "gemini": "https://gemini.google.com",
    "perplexity": "https://www.perplexity.ai",
    "perplexity.ai": "https://www.perplexity.ai",
    "youtube": "https://youtube.com",
    "youtube.com": "https://youtube.com",
    "google": "https://google.com",
    "google.com": "https://google.com",
    "gmail": "https://gmail.com",
    "gmail.com": "https://gmail.com",
    "drive.google.com": "https://drive.google.com",
    "google drive": "https://drive.google.com",
    "netflix": "https://netflix.com",
    "spotify": "https://open.spotify.com",
    "twitter": "https://twitter.com",
    "x.com": "https://x.com",
    "twitter.com": "https://twitter.com",
    "linkedin": "https://linkedin.com",
    "reddit": "https://reddit.com",
    "instagram": "https://instagram.com",
    "facebook": "https://facebook.com",
    "amazon": "https://amazon.com",
    "flipkart": "https://flipkart.com",
    "wikipedia": "https://wikipedia.org",
    "medium": "https://medium.com",
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

    def _format_research_with_llm(self, query: str, raw_text: str, sources: list = None) -> str:
        """Use LLM to format raw scraped text into a well-structured research document."""
        try:
            from groq import Groq
            api_key = self.config.get_active_api_key()
            if not api_key:
                logger.warning("No API key for research formatting, using raw text")
                return raw_text

            client = Groq(api_key=api_key)
            
            sources_block = ""
            if sources:
                sources_block = "\n\nSources consulted:\n" + "\n".join(f"- {s}" for s in sources)
            
            # Truncate raw text to avoid overwhelming the LLM
            raw_text_truncated = raw_text[:25000]
            
            prompt = f"""You are an elite research analyst. Produce a COMPREHENSIVE, DETAILED research document about "{query}".

REQUIREMENTS:
1. The document MUST be at least 2000 words with ALL 7 chapters listed below.
2. Each chapter MUST have at least 2-3 detailed paragraphs.
3. Use REAL data, statistics, dates, names, company references wherever possible.
4. Write in a professional, authoritative tone.
5. Do NOT use markdown code blocks. Use plain text with section headers.

MANDATORY 7-CHAPTER STRUCTURE:

CHAPTER 1: EXECUTIVE SUMMARY & OVERVIEW
CHAPTER 2: HISTORICAL CONTEXT & EVOLUTION  
CHAPTER 3: CORE ARCHITECTURE & TECHNICAL PRINCIPLES
CHAPTER 4: KEY APPLICATIONS & USE CASES
CHAPTER 5: MAJOR CHALLENGES & LIMITATIONS
CHAPTER 6: FUTURE PROJECTIONS & STRATEGIC ROADMAP
CHAPTER 7: COMPARATIVE ANALYSIS & CONCLUDING ANALYSIS
{sources_block}

RAW SCRAPED CONTENT:
{raw_text_truncated}

WRITE THE COMPLETE RESEARCH DOCUMENT. AT LEAST 2000 WORDS, ALL 7 CHAPTERS."""

            best_output = ""
            for attempt in range(1, 4):
                try:
                    resp = client.chat.completions.create(
                        model=self.config.LLM_MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.6,
                        max_tokens=8000,
                    )
                    result = resp.choices[0].message.content.strip()
                    word_count = len(result.split())
                    logger.info(f"Research LLM attempt {attempt}: {word_count} words")
                    
                    if word_count >= 1500:
                        return result
                    
                    if len(result) > len(best_output):
                        best_output = result
                        
                    if attempt < 3:
                        logger.warning(f"Research attempt {attempt} short ({word_count} words), retrying...")
                except Exception as retry_err:
                    logger.warning(f"Research LLM attempt {attempt} failed: {retry_err}")
                    if attempt < 3:
                        time.sleep(2)
            
            if best_output and len(best_output) > 100:
                return best_output
            
            return raw_text
        except Exception as e:
            logger.error(f"LLM research formatting failed: {e}")
            return raw_text

    def _clean_old_cache(self):
        try:
            now = time.time()
            cleaned = 0
            for f in CACHE_DIR.glob("*.*"):
                try:
                    if now - f.stat().st_mtime > 48 * 3600:
                        f.unlink()
                        cleaned += 1
                except Exception:
                    pass
            if cleaned > 0:
                logger.info(f"Cleaned {cleaned} old cache files")
        except Exception as e:
            logger.warning(f"Cache cleanup failed: {e}")

    def resolve_accurate_url_sync(self, query: str) -> str:
        """
        Pure synchronous URL resolver. 100% immune to Asyncio loop crashes.
        3-layer resolution: Safe Map -> Web Fallback Map -> Search Validation
        """
        original_query = query.strip()
        clean_query = original_query.lower().strip()
        
        # Strip common noise words that get concatenated with URLs
        noise_words = [
            "open", "karo", "kholo", "launch", "start", "new tab", "browser",
            "mein", "me", "tab", "website", "site", "page", "url", "link",
            "please", "pls", "kar", "do", "na", "bhi", "andar"
        ]
        
        # Remove noise words from query
        query_cleaned = clean_query
        for noise in sorted(noise_words, key=len, reverse=True):
            query_cleaned = query_cleaned.replace(noise, " ")
        query_cleaned = query_cleaned.strip()
        
        # If original has http/https, use it directly
        if original_query.startswith(("http://", "https://")):
            return original_query
        
        # Pre-validation for concatenated phrases (e.g. "newtabyoutubeopenkaro")
        if "." not in clean_query and "/" not in clean_query:
            if len(clean_query) > 20:
                COMMON_SITES = [
                    "youtube", "google", "github", "netflix", "facebook", "instagram", 
                    "twitter", "linkedin", "amazon", "flipkart", "reddit", "wikipedia",
                    "yahoo", "bing", "chatgpt", "openai", "claude", "anthropic", 
                    "gemini", "apple", "microsoft", "spotify", "twitch", "discord",
                    "zoom", "slack", "notion", "figma", "canva", "pinterest", 
                    "tiktok", "snapchat", "whatsapp", "telegram", "quora", "medium",
                    "vimeo", "dailymotion", "soundcloud", "imdb", "booking",
                    "airbnb", "uber", "zomato", "swiggy", "myntra", "nykaa", 
                    "makemytrip", "cleartrip", "x"
                ]
                found_site = ""
                for site in COMMON_SITES:
                    if site in clean_query:
                        if len(site) > len(found_site):
                            found_site = site
                
                if found_site:
                    return f"https://{found_site}.com"
                else:
                    # Try search validation
                    try:
                        encoded = quote_plus(original_query)
                        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1"
                        with httpx.Client(timeout=4.0) as client:
                            resp = client.get(url)
                            if resp.status_code == 200:
                                data = resp.json()
                                abstract_url = data.get("AbstractURL", "")
                                if abstract_url:
                                    return abstract_url
                    except Exception as e:
                        logger.warning(f"Search validation failed: {e}")
                    
                    return f"https://duckduckgo.com/?q={quote_plus(original_query)}"

        # Layer 1: Core Map Check (exact match first)
        if query_cleaned in CORE_DEVELOPER_MAP:
            return CORE_DEVELOPER_MAP[query_cleaned]
        if clean_query in CORE_DEVELOPER_MAP:
            return CORE_DEVELOPER_MAP[clean_query]
        
        # Substring match in core map
        for key, url in CORE_DEVELOPER_MAP.items():
            if key == query_cleaned or key == clean_query:
                return url
            # Check if the key is contained in the query (for multi-word matches)
            if key in query_cleaned and len(key) > 3:
                return url

        # Layer 2: Web Fallback Map
        try:
            from config import config as cfg
            web_map = getattr(cfg, 'WEB_FALLBACK_MAP', {})
            if clean_query in web_map:
                return web_map[clean_query]
            if query_cleaned in web_map:
                return web_map[query_cleaned]
            for key, url in web_map.items():
                if key in query_cleaned and len(key) > 3:
                    return url
                if key in clean_query and len(key) > 3:
                    return url
        except Exception as e:
            logger.warning(f"Web fallback map failed: {e}")

        # Layer 3: Search Engine Validation
        try:
            encoded = quote_plus(original_query)
            url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1"
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    abstract_url = data.get("AbstractURL", "")
                    if abstract_url:
                        return abstract_url
                    
                    # Try related topics
                    related = data.get("RelatedTopics", [])
                    for topic in related[:5]:
                        if isinstance(topic, dict):
                            first_url = topic.get("FirstURL", "")
                            if first_url:
                                return first_url
        except Exception as e:
            logger.warning(f"Search validation failed: {e}")

        # Last resort: try to construct URL
        _NON_WEB_FALLBACK = {
            "browser", "app", "application", "settings", "system", "desktop",
            "screen", "window", "folder", "file", "document", "music",
            "video", "photo", "camera", "store", "help", "search",
            "terminal", "console", "editor", "player", "recorder",
            "manager", "monitor", "control", "panel", "tool",
        }
        
        # Check if cleaned query looks like a domain
        if "." in original_query and " " not in original_query:
            # Looks like a domain
            if not original_query.startswith(("http://", "https://")):
                return f"https://{original_query}"
            return original_query
        
        fallback = original_query.replace(" ", "").lower()
        if fallback in _NON_WEB_FALLBACK:
            logger.warning(f"Refusing to convert '{original_query}' to a .com domain")
            return ""
        
        # Final fallback: construct from cleaned query
        domain_candidate = query_cleaned.replace(" ", "").replace("_", "")
        if domain_candidate and "." in domain_candidate:
            return f"https://{domain_candidate}" if not domain_candidate.startswith("http") else domain_candidate
        
        if domain_candidate and len(domain_candidate) > 1:
            return f"https://{domain_candidate}.com"
        
        return f"https://duckduckgo.com/?q={quote_plus(original_query)}"

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
            tts_callback("undetected-chromedriver library is missing. Install it first.", None)
            return

        driver = None
        try:
            options = uc.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--window-position=-32000,-32000")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0")
            
            user_data = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
            if os.path.exists(user_data):
                options.add_argument(f"--user-data-dir={user_data}")
                options.add_argument("--profile-directory=Default")

            clean_query = raw_query.strip()
            looks_like_url = any(clean_query.lower().startswith(p) for p in ("http://", "https://", "www.")) \
                             or ("." in clean_query and " " not in clean_query)

            driver = uc.Chrome(options=options, version_main=None)
            driver.set_page_load_timeout(30)
            
            # Execute CDP to prevent detection
            try:
                driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                    'source': '''
                        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                    '''
                })
            except Exception:
                pass
            
            all_scraped_text = ""
            sources_visited = []

            if looks_like_url:
                target_url = self.resolve_accurate_url_sync(clean_query)
                sources_visited.append(target_url)
                logger.info(f"[Research] Deep-scraping single URL: {target_url}")
                
                page_text = self._deep_scrape_page(driver, target_url)
                if page_text:
                    all_scraped_text = page_text
            else:
                search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(clean_query)}"
                logger.info(f"[Research] Searching: {search_url}")
                
                result_urls = self._extract_search_result_urls(driver, search_url)
                
                if not result_urls:
                    logger.warning("DuckDuckGo returned no results, trying Google fallback")
                    google_url = f"https://www.google.com/search?q={quote_plus(clean_query)}"
                    result_urls = self._extract_google_result_urls(driver, google_url)
                
                if not result_urls:
                    logger.warning("No result URLs found, scraping search page directly")
                    page_text = self._deep_scrape_page(driver, search_url)
                    if page_text:
                        all_scraped_text = page_text
                        sources_visited.append(search_url)
                else:
                    max_sites = min(len(result_urls), 5)
                    logger.info(f"Found {len(result_urls)} URLs, visiting top {max_sites}")
                    
                    for i, url in enumerate(result_urls[:max_sites]):
                        try:
                            logger.info(f"[Research] Scraping site {i+1}/{max_sites}: {url}")
                            page_text = self._deep_scrape_page(driver, url)
                            
                            if page_text and len(page_text.strip()) > 100:
                                source_header = f"\n\n{'='*40}\nSOURCE {i+1}: {url}\n{'='*40}\n"
                                all_scraped_text += source_header + page_text
                                sources_visited.append(url)
                                logger.info(f"Site {i+1} scraped: {len(page_text)} chars")
                            else:
                                logger.warning(f"Site {i+1} returned insufficient content")
                            
                            if i < max_sites - 1:
                                time.sleep(2)
                        except Exception as site_err:
                            logger.warning(f"Failed to scrape site {i+1}: {site_err}")
                            continue
                    
                    if len(all_scraped_text.strip()) < 200:
                        logger.warning("Multi-site scraping yielded too little, trying search page")
                        page_text = self._deep_scrape_page(driver, search_url)
                        if page_text:
                            all_scraped_text = page_text
                            sources_visited = [search_url]

            driver.quit()
            driver = None

            # Fallback: if Selenium scraped nothing, try httpx
            if len(all_scraped_text.strip()) < 200:
                logger.warning("Selenium scraping insufficient, trying httpx fallback")
                all_scraped_text = self._httpx_fallback_scrape(clean_query)
                sources_visited = ["httpx-fallback"]

            word_count = len(all_scraped_text.split())
            logger.info(f"Total scraped: {len(all_scraped_text)} chars, {word_count} words from {len(sources_visited)} sources")

            if word_count > 50:
                formatted_text = self._format_research_with_llm(raw_query, all_scraped_text, sources_visited)

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = re.sub(r'[^a-zA-Z0-9]', '_', raw_query)[:30]
                file_path = CACHE_DIR / f"Research_{safe_name}_{ts}.txt"
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"{'='*70}\n")
                    f.write(f"  MAX DEEP RESEARCH REPORT: {raw_query.upper()}\n")
                    f.write(f"{'='*70}\n")
                    f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Sources Consulted: {len(sources_visited)}\n")
                    for idx, src in enumerate(sources_visited, 1):
                        f.write(f"  [{idx}] {src}\n")
                    f.write(f"{'='*70}\n\n")
                    f.write(formatted_text)

                report_words = len(formatted_text.split())
                tts_callback(
                    f"Deep research complete! I've created a {report_words}-word detailed report on {raw_query} from {len(sources_visited)} sources. It's saved in your research cache folder.",
                    {"status": "file_saved", "file_path": str(file_path.absolute()), "word_count": report_words, "sources": len(sources_visited)}
                )
            else:
                tts_callback(f"Sorry, I couldn't gather enough information about {raw_query}. The websites didn't return sufficient content.", {"status": "insufficient_data"})

        except Exception as e:
            logger.error(f"Selenium Autopilot Loop failed: {e}")
            if driver:
                try: 
                    driver.quit()
                except Exception: 
                    pass
            tts_callback(f"Research failed due to an error. You can try again.", None)

    def _deep_scrape_page(self, driver, url: str) -> str:
        """Navigate to a URL and extract maximum text content with Cloudflare handling."""
        try:
            driver.get(url)
            time.sleep(2.5)
            
            # Cloudflare / bot detection wait
            page_title = driver.title.lower() if driver.title else ""
            cf_indicators = ["just a moment", "cloudflare", "checking your browser", "attention required"]
            if any(kw in page_title for kw in cf_indicators):
                logger.info(f"Cloudflare detected on {url}, waiting...")
                for wait_attempt in range(1, 10):
                    time.sleep(2.0)
                    updated_title = driver.title.lower() if driver.title else ""
                    if not any(kw in updated_title for kw in cf_indicators):
                        logger.info(f"Cloudflare bypassed after {wait_attempt * 2}s")
                        break
                else:
                    logger.warning(f"Cloudflare blocked on {url}, skipping")
                    return ""
            
            # Wait for body to load
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except Exception:
                pass
            
            scraped_parts = []
            
            # Layer 1: Paragraphs (richest content)
            try:
                paragraphs = driver.find_elements(By.TAG_NAME, "p")
                for p in paragraphs[:80]:
                    text = p.text.strip()
                    if len(text) > 25:
                        scraped_parts.append(text)
            except Exception:
                pass
            
            # Layer 2: Article and section elements
            for tag in ["article", "section", "main"]:
                try:
                    elements = driver.find_elements(By.TAG_NAME, tag)
                    for el in elements[:10]:
                        text = el.text.strip()
                        if len(text) > 50:
                            scraped_parts.append(text)
                except Exception:
                    pass
            
            # Layer 3: Headings for structure
            for htag in ["h1", "h2", "h3"]:
                try:
                    headings = driver.find_elements(By.TAG_NAME, htag)
                    for h in headings[:20]:
                        text = h.text.strip()
                        if len(text) > 5:
                            scraped_parts.append(f"[{htag.upper()}] {text}")
                except Exception:
                    pass
            
            # Layer 4: List items for supplementary data
            try:
                lis = driver.find_elements(By.TAG_NAME, "li")
                for li in lis[:40]:
                    text = li.text.strip()
                    if 20 < len(text) < 500:
                        scraped_parts.append(f"- {text}")
            except Exception:
                pass
            
            # Layer 5: If still insufficient, grab full body text
            combined = "\n".join(scraped_parts)
            if len(combined) < 500:
                try:
                    body = driver.find_element(By.TAG_NAME, "body")
                    body_text = body.text
                    lines = [l.strip() for l in body_text.split("\n") if l.strip() and len(l.strip()) > 10]
                    combined = "\n".join(lines[:250])
                except Exception:
                    pass
            
            # Deduplicate
            seen = set()
            deduped = []
            for line in combined.split("\n"):
                line_clean = line.strip()
                if line_clean and line_clean not in seen and len(line_clean) > 10:
                    seen.add(line_clean)
                    deduped.append(line_clean)
            
            return "\n".join(deduped)
            
        except Exception as e:
            logger.warning(f"Deep scrape failed for {url}: {e}")
            return ""

    def _extract_search_result_urls(self, driver, search_url: str) -> list:
        """Extract organic result URLs from DuckDuckGo HTML search results."""
        try:
            driver.get(search_url)
            time.sleep(3.0)
            
            urls = []
            # DuckDuckGo HTML version uses <a class="result__a"> for result links
            try:
                links = driver.find_elements(By.CSS_SELECTOR, "a.result__a")
                for link in links[:12]:
                    href = link.get_attribute("href") or ""
                    if "uddg=" in href:
                        try:
                            parsed = urlparse(href)
                            params = parse_qs(parsed.query)
                            if "uddg" in params:
                                href = unquote(params["uddg"][0])
                        except Exception:
                            pass
                    
                    if href and href.startswith("http") and "duckduckgo" not in href.lower():
                        skip_domains = [
                            "youtube.com/watch", "reddit.com/r/", "twitter.com/i/",
                            "x.com/i/", "facebook.com/", "instagram.com/"
                        ]
                        if not any(sd in href.lower() for sd in skip_domains):
                            urls.append(href)
            except Exception as e:
                logger.warning(f"DuckDuckGo link extraction failed: {e}")
            
            # Fallback: generic link extraction
            if not urls:
                try:
                    all_links = driver.find_elements(By.TAG_NAME, "a")
                    for link in all_links:
                        href = link.get_attribute("href") or ""
                        if href.startswith("https://") and "duckduckgo" not in href.lower() and len(href) > 20:
                            urls.append(href)
                            if len(urls) >= 10:
                                break
                except Exception:
                    pass
            
            # Deduplicate while preserving order
            seen = set()
            unique_urls = []
            for u in urls:
                try:
                    domain = urlparse(u).netloc
                    if domain not in seen:
                        seen.add(domain)
                        unique_urls.append(u)
                except Exception:
                    if u not in seen:
                        seen.add(u)
                        unique_urls.append(u)
            
            return unique_urls
            
        except Exception as e:
            logger.warning(f"Search result URL extraction failed: {e}")
            return []

    def _extract_google_result_urls(self, driver, google_url: str) -> list:
        """Fallback: extract result URLs from Google search results."""
        try:
            driver.get(google_url)
            time.sleep(3.0)
            
            urls = []
            try:
                containers = driver.find_elements(By.CSS_SELECTOR, "div.g a, div[data-hveid] a")
                for link in containers[:12]:
                    href = link.get_attribute("href") or ""
                    if href.startswith("http") and "google.com" not in href:
                        skip_domains = ["youtube.com/watch", "reddit.com/r/", "twitter.com/i/", "x.com/i/"]
                        if not any(sd in href.lower() for sd in skip_domains):
                            urls.append(href)
            except Exception:
                pass
            
            # Deduplicate
            seen = set()
            unique = []
            for u in urls:
                try:
                    domain = urlparse(u).netloc
                    if domain not in seen:
                        seen.add(domain)
                        unique.append(u)
                except Exception:
                    if u not in seen:
                        seen.add(u)
                        unique.append(u)
            
            return unique
            
        except Exception as e:
            logger.warning(f"Google fallback URL extraction failed: {e}")
            return []

    def _httpx_fallback_scrape(self, query: str) -> str:
        """Non-Selenium fallback: use httpx to fetch content."""
        scraped = ""
        try:
            # Try Wikipedia first
            wiki_safe = re.sub(r'[^a-zA-Z0-9_\s-]', '', query).strip()
            wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote_plus(wiki_safe)}"
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(wiki_url)
                if resp.status_code == 200:
                    data = resp.json()
                    extract = data.get("extract", "")
                    if extract and len(extract) > 100:
                        scraped += f"[Wikipedia Summary]\n{extract}\n\n"
            
            # Try DuckDuckGo instant answer
            ddg_url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1"
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(ddg_url)
                if resp.status_code == 200:
                    data = resp.json()
                    abstract = data.get("AbstractText", "")
                    if abstract:
                        scraped += f"[DuckDuckGo Abstract]\n{abstract}\n\n"
                    for topic in data.get("RelatedTopics", [])[:15]:
                        if isinstance(topic, dict) and "Text" in topic:
                            scraped += f"- {topic['Text']}\n"
            
            logger.info(f"httpx fallback scraped {len(scraped)} chars")
        except Exception as e:
            logger.warning(f"httpx fallback failed: {e}")
        
        return scraped
