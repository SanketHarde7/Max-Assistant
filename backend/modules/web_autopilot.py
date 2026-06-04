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

    def _format_research_with_llm(self, query: str, raw_text: str, sources: list = None) -> str:
        """Use LLM to format raw scraped text into a massive, well-structured research document."""
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
            
            prompt = f"""You are an elite research analyst and technical writer. Your task is to produce a MASSIVE, COMPREHENSIVE, and EXTREMELY DETAILED research document about "{query}".

ABSOLUTE REQUIREMENTS — VIOLATION IS UNACCEPTABLE:
1. The document MUST be AT LEAST 3000 words (approximately 5+ printed pages). Shorter output = FAILURE.
2. The document MUST contain ALL 7 chapters listed below. Do NOT skip any chapter.
3. Each chapter MUST have at least 3-4 detailed paragraphs (each paragraph = 4-6 sentences minimum).
4. Use REAL data, statistics, dates, names, company references, and technical details wherever possible.
5. If the scraped content is thin on some areas, EXPAND with your own expert knowledge on the topic.
6. Write in a professional, authoritative, academic tone — as if writing for a university research paper or a professional tech report.
7. Do NOT use markdown code blocks. Use plain text with clear section headers using === and --- separators.

MANDATORY 7-CHAPTER STRUCTURE:

================================================================
CHAPTER 1: EXECUTIVE SUMMARY & OVERVIEW
================================================================
- What is this topic? Define it clearly and comprehensively.
- Why does it matter? What is its significance in the broader landscape?
- Key statistics, market size, adoption rates, or scale of impact.
- Brief roadmap of what the rest of the document covers.

================================================================
CHAPTER 2: HISTORICAL CONTEXT & EVOLUTION
================================================================
- Origins and early development (dates, key people, founding moments).
- Major milestones and breakthroughs over time (timeline format encouraged).
- How the field has evolved decade by decade or era by era.
- Pivotal moments that changed the trajectory.

================================================================
CHAPTER 3: CORE ARCHITECTURE & TECHNICAL PRINCIPLES
================================================================
- Deep technical explanation of how it works under the hood.
- Key components, algorithms, protocols, or mechanisms.
- Technical diagrams described in text (layers, data flow, architecture).
- Comparisons with alternative approaches and why this design was chosen.

================================================================
CHAPTER 4: KEY APPLICATIONS & USE CASES
================================================================
- At least 5-6 real-world applications with specific examples.
- Industry-specific use cases (healthcare, finance, defense, education, etc.).
- Case studies or notable deployments (name companies, projects, results).
- Emerging and experimental applications.

================================================================
CHAPTER 5: MAJOR CHALLENGES & LIMITATIONS
================================================================
- Technical challenges and unsolved problems.
- Economic, social, or ethical concerns.
- Security and privacy implications.
- Scalability and adoption barriers.
- Current debates and controversies in the field.

================================================================
CHAPTER 6: FUTURE PROJECTIONS & STRATEGIC ROADMAP
================================================================
- Near-term developments (1-3 years).
- Medium-term trajectory (3-10 years).
- Long-term vision and transformative potential.
- Expert predictions and forecasts (cite real researchers/organizations if possible).
- Potential paradigm shifts.

================================================================
CHAPTER 7: COMPARATIVE ANALYSIS & CONCLUDING ANALYSIS
================================================================
- Compare with competing or related technologies/approaches.
- Strengths vs weaknesses summary table (described in text).
- Final synthesis: What does all this mean?
- Recommendations for stakeholders (researchers, businesses, policymakers).
- Closing thoughts on the topic's ultimate trajectory.
{sources_block}

RAW SCRAPED CONTENT FROM MULTIPLE WEBSITES:
{raw_text[:30000]}

NOW WRITE THE COMPLETE RESEARCH DOCUMENT. REMEMBER: AT LEAST 3000 WORDS, ALL 7 CHAPTERS, MAXIMUM DETAIL."""

            # Retry logic: attempt up to 3 times if LLM output is too short
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
                    logger.info(f"Research LLM attempt {attempt}: {word_count} words generated")
                    
                    if word_count >= 1500:
                        return result
                    
                    # Keep the longest attempt
                    if len(result) > len(best_output):
                        best_output = result
                        
                    if attempt < 3:
                        logger.warning(f"Research attempt {attempt} too short ({word_count} words), retrying...")
                except Exception as retry_err:
                    logger.warning(f"Research LLM attempt {attempt} failed: {retry_err}")
                    if attempt < 3:
                        time.sleep(2)
            
            # Return best attempt even if short
            if best_output and len(best_output) > 100:
                return best_output
            
            logger.warning("All LLM research attempts produced short output, using raw text")
            return raw_text
        except Exception as e:
            logger.error(f"LLM research formatting completely failed: {e}")
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

        # Layer 2: Sync Domain Corrector (WEB_FALLBACK_MAP)
        try:
            from config import config
            web_map = getattr(config, 'WEB_FALLBACK_MAP', {})
            if clean_query in web_map:
                return web_map[clean_query]
            for key, url in web_map.items():
                if key in clean_query or clean_query in key:
                    return url
        except Exception as e:
            logger.warning(f"[Sync Layer 2] Domain corrector failed: {e}")

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

        # Last resort cleaner — but don't blindly convert non-web words to domains
        _NON_WEB_FALLBACK = {
            "browser", "app", "application", "settings", "system", "desktop",
            "screen", "window", "folder", "file", "document", "music",
            "video", "photo", "camera", "store", "help", "search",
            "terminal", "console", "editor", "player", "recorder",
            "manager", "monitor", "control", "panel", "tool",
        }
        fallback = query.replace(" ", "").lower()
        if fallback in _NON_WEB_FALLBACK:
            logger.warning(f"[Sync] Refusing to convert '{query}' to a .com domain — it's not a website.")
            return ""
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
            options.add_argument("--disable-blink-features=AutomationControlled")
            
            user_data = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
            if os.path.exists(user_data):
                options.add_argument(f"--user-data-dir={user_data}")
                options.add_argument("--profile-directory=Default")

            clean_query = raw_query.strip()
            looks_like_url = any(clean_query.lower().startswith(p) for p in ("http://", "https://", "www.")) \
                             or ("." in clean_query and " " not in clean_query)

            driver = uc.Chrome(options=options, version_main=None)
            driver.set_page_load_timeout(30)
            
            all_scraped_text = ""
            sources_visited = []

            if looks_like_url:
                # ── Single URL deep scrape ──
                target_url = self.resolve_accurate_url_sync(clean_query)
                sources_visited.append(target_url)
                logger.info(f"[Research] Deep-scraping single URL: {target_url}")
                
                page_text = self._deep_scrape_page(driver, target_url)
                if page_text:
                    all_scraped_text = page_text
            else:
                # ── Multi-site research: discover top links from DuckDuckGo, visit each ──
                search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(clean_query)}"
                logger.info(f"[Research] Fetching search results from: {search_url}")
                
                result_urls = self._extract_search_result_urls(driver, search_url)
                
                if not result_urls:
                    # Fallback: try Google search to find links
                    logger.warning("[Research] DuckDuckGo returned no results, trying Google fallback")
                    google_url = f"https://www.google.com/search?q={quote_plus(clean_query)}"
                    result_urls = self._extract_google_result_urls(driver, google_url)
                
                if not result_urls:
                    # Last resort: scrape the search page itself
                    logger.warning("[Research] No result URLs found, scraping search page directly")
                    page_text = self._deep_scrape_page(driver, search_url)
                    if page_text:
                        all_scraped_text = page_text
                        sources_visited.append(search_url)
                else:
                    # Visit top 5 result URLs sequentially and scrape each
                    max_sites = min(len(result_urls), 5)
                    logger.info(f"[Research] Found {len(result_urls)} result URLs, visiting top {max_sites}")
                    
                    for i, url in enumerate(result_urls[:max_sites]):
                        try:
                            logger.info(f"[Research] Scraping site {i+1}/{max_sites}: {url}")
                            page_text = self._deep_scrape_page(driver, url)
                            
                            if page_text and len(page_text.strip()) > 100:
                                source_header = f"\n\n{'='*40}\nSOURCE {i+1}: {url}\n{'='*40}\n"
                                all_scraped_text += source_header + page_text
                                sources_visited.append(url)
                                logger.info(f"[Research] Site {i+1} scraped: {len(page_text)} chars")
                            else:
                                logger.warning(f"[Research] Site {i+1} returned insufficient content, skipping")
                            
                            # Don't hammer servers — small delay between sites
                            if i < max_sites - 1:
                                time.sleep(1.5)
                                
                        except Exception as site_err:
                            logger.warning(f"[Research] Failed to scrape site {i+1} ({url}): {site_err}")
                            continue
                    
                    # If multi-site scraping yielded nothing, fallback to search page
                    if len(all_scraped_text.strip()) < 200:
                        logger.warning("[Research] Multi-site scraping yielded too little, scraping search page")
                        page_text = self._deep_scrape_page(driver, search_url)
                        if page_text:
                            all_scraped_text = page_text
                            sources_visited = [search_url]

            driver.quit()
            driver = None

            # ── Fallback: if Selenium scraped nothing, try httpx text scrape ──
            if len(all_scraped_text.strip()) < 200:
                logger.warning("[Research] Selenium scraping insufficient, trying httpx fallback")
                all_scraped_text = self._httpx_fallback_scrape(clean_query)
                sources_visited = ["httpx-fallback"]

            word_count = len(all_scraped_text.split())
            logger.info(f"[Research] Total scraped: {len(all_scraped_text)} chars, {word_count} words from {len(sources_visited)} sources")

            if word_count > 50:
                # Format raw content into a proper research document via LLM
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
                tts_callback(f"Sorry boss, I couldn't gather enough information about {raw_query}. The websites didn't return sufficient content.", {"status": "insufficient_data"})

        except Exception as e:
            logger.error(f"Selenium Autopilot Loop exploded: {e}")
            if driver:
                try: driver.quit()
                except Exception: pass
            tts_callback(f"Sorry boss, research failed due to an error. I'll try again if you ask.", None)

    def _deep_scrape_page(self, driver, url: str) -> str:
        """Navigate to a URL and extract maximum text content with Cloudflare handling."""
        try:
            driver.get(url)
            time.sleep(3.0)
            
            # Cloudflare / bot detection wait
            page_title = driver.title.lower() if driver.title else ""
            if any(kw in page_title for kw in ["just a moment", "cloudflare", "checking your browser", "attention required"]):
                logger.info(f"[Research] Cloudflare detected on {url}, waiting...")
                for wait_attempt in range(1, 8):
                    time.sleep(2.5)
                    updated_title = driver.title.lower() if driver.title else ""
                    if not any(kw in updated_title for kw in ["just a moment", "cloudflare", "checking your browser"]):
                        logger.info(f"[Research] Cloudflare bypassed after {wait_attempt * 2.5}s")
                        break
                else:
                    logger.warning(f"[Research] Cloudflare blocked on {url}, skipping")
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
                for p in paragraphs[:60]:
                    text = p.text.strip()
                    if len(text) > 30:
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
                for li in lis[:30]:
                    text = li.text.strip()
                    if 20 < len(text) < 500:
                        scraped_parts.append(f"• {text}")
            except Exception:
                pass
            
            # Layer 5: If still insufficient, grab full body text
            combined = "\n".join(scraped_parts)
            if len(combined) < 500:
                try:
                    body = driver.find_element(By.TAG_NAME, "body")
                    body_text = body.text
                    lines = [l.strip() for l in body_text.split("\n") if l.strip() and len(l.strip()) > 10]
                    combined = "\n".join(lines[:200])
                except Exception:
                    pass
            
            # Deduplicate (some content may appear in both <p> and <article>)
            seen = set()
            deduped = []
            for line in combined.split("\n"):
                line_clean = line.strip()
                if line_clean and line_clean not in seen and len(line_clean) > 10:
                    seen.add(line_clean)
                    deduped.append(line_clean)
            
            return "\n".join(deduped)
            
        except Exception as e:
            logger.warning(f"[Research] Deep scrape failed for {url}: {e}")
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
                for link in links[:10]:
                    href = link.get_attribute("href") or ""
                    # DuckDuckGo wraps URLs with redirect — extract the actual URL
                    if "uddg=" in href:
                        from urllib.parse import unquote, urlparse, parse_qs
                        parsed = urlparse(href)
                        params = parse_qs(parsed.query)
                        if "uddg" in params:
                            href = unquote(params["uddg"][0])
                    
                    if href and href.startswith("http") and "duckduckgo" not in href:
                        # Skip non-content URLs
                        skip_domains = ["youtube.com", "reddit.com/r/", "twitter.com", "x.com", "facebook.com", "instagram.com"]
                        if not any(sd in href.lower() for sd in skip_domains):
                            urls.append(href)
            except Exception as e:
                logger.warning(f"[Research] DuckDuckGo link extraction failed: {e}")
            
            # Fallback: generic <a> tags with result-like hrefs
            if not urls:
                try:
                    all_links = driver.find_elements(By.TAG_NAME, "a")
                    for link in all_links:
                        href = link.get_attribute("href") or ""
                        if href.startswith("https://") and "duckduckgo" not in href and len(href) > 20:
                            urls.append(href)
                            if len(urls) >= 8:
                                break
                except Exception:
                    pass
            
            # Deduplicate while preserving order
            seen = set()
            unique_urls = []
            for u in urls:
                domain = u.split("/")[2] if len(u.split("/")) > 2 else u
                if domain not in seen:
                    seen.add(domain)
                    unique_urls.append(u)
            
            return unique_urls
            
        except Exception as e:
            logger.warning(f"[Research] Search result URL extraction failed: {e}")
            return []

    def _extract_google_result_urls(self, driver, google_url: str) -> list:
        """Fallback: extract result URLs from Google search results."""
        try:
            driver.get(google_url)
            time.sleep(3.0)
            
            urls = []
            try:
                # Google uses <a> tags with /url?q= redirects or direct links in <div class="g">
                containers = driver.find_elements(By.CSS_SELECTOR, "div.g a")
                for link in containers[:10]:
                    href = link.get_attribute("href") or ""
                    if href.startswith("http") and "google.com" not in href:
                        skip_domains = ["youtube.com", "reddit.com/r/", "twitter.com", "x.com"]
                        if not any(sd in href.lower() for sd in skip_domains):
                            urls.append(href)
            except Exception:
                pass
            
            # Deduplicate
            seen = set()
            unique = []
            for u in urls:
                domain = u.split("/")[2] if len(u.split("/")) > 2 else u
                if domain not in seen:
                    seen.add(domain)
                    unique.append(u)
            
            return unique
            
        except Exception as e:
            logger.warning(f"[Research] Google fallback URL extraction failed: {e}")
            return []

    def _httpx_fallback_scrape(self, query: str) -> str:
        """Non-Selenium fallback: use httpx to fetch Wikipedia or search snippets."""
        scraped = ""
        try:
            # Try Wikipedia first — usually has the richest content
            wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote_plus(query)}"
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(wiki_url)
                if resp.status_code == 200:
                    data = resp.json()
                    extract = data.get("extract", "")
                    if extract and len(extract) > 100:
                        scraped += f"[Wikipedia Summary]\n{extract}\n\n"
            
            # Also try DuckDuckGo instant answer API
            ddg_url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1"
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(ddg_url)
                if resp.status_code == 200:
                    data = resp.json()
                    abstract = data.get("AbstractText", "")
                    if abstract:
                        scraped += f"[DuckDuckGo Abstract]\n{abstract}\n\n"
                    # Related topics
                    for topic in data.get("RelatedTopics", [])[:10]:
                        if isinstance(topic, dict) and "Text" in topic:
                            scraped += f"• {topic['Text']}\n"
            
            logger.info(f"[Research] httpx fallback scraped {len(scraped)} chars")
        except Exception as e:
            logger.warning(f"[Research] httpx fallback failed: {e}")
        
        return scraped