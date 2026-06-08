# Path: backend/modules/browser_agent.py
# Use: Automates operations and searches inside web browsers.
# browser_agent.py — MAX v4.1
# Selenium-based browser automation with driver reuse.
# Skills: browser_open, browser_click, browser_type, browser_scrape
import logging
import asyncio
from typing import Optional, Dict, Any
from config import config

logger = logging.getLogger("MAX.BROWSER")


def _url_to_label(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return "Website"
    raw = raw.replace("https://", "").replace("http://", "")
    raw = raw.replace("www.", "")
    raw = raw.split("/")[0]
    raw = raw.split("?")[0].split("#")[0].split(":")[0]
    name = raw.split(".")[0] if raw else "Website"
    return name.capitalize() if name else "Website"


def _normalize_url(url: str) -> str:
    """Normalize URL: add https:// and .com if needed."""
    url = url.strip()
    if not url:
        return ""
    
    # Already has protocol
    if url.startswith(("http://", "https://")):
        return url
    
    # Has dot but no protocol - add https
    if "." in url:
        return f"https://{url}"
    
    # No dot, no protocol - assume .com
    return f"https://{url}.com"


class BrowserAgent:
    """Lightweight Selenium browser agent with driver reuse."""

    def __init__(self):
        self._driver = None
        self._last_url = None
        self.headless = config.BROWSER_HEADLESS
        self.timeout = config.BROWSER_TIMEOUT
        self._error_count = 0
        self._max_errors = 3

    def _create_driver(self):
        """Create a new Selenium driver instance."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.options import Options

            options = Options()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            
            # Execute CDP to prevent detection
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                '''
            })
            
            driver.set_page_load_timeout(self.timeout)
            self._error_count = 0  # Reset error count on success
            logger.info("Browser driver created successfully")
            return driver
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Browser init failed: {e}")
            return None

    def _get_driver(self):
        """Get existing driver or create new one. Includes health check."""
        if self._driver is not None:
            try:
                # Health check
                handles = self._driver.window_handles
                if not handles:
                    raise Exception("No window handles")
                return self._driver
            except Exception:
                logger.info("Existing browser driver session dead. Creating new instance...")
                try:
                    self._driver.quit()
                except Exception:
                    pass
                self._driver = None
        
        if self._driver is None:
            self._driver = self._create_driver()
        
        return self._driver

    def _ensure_driver(self) -> str:
        d = self._get_driver()
        if d is None:
            return "Browser could not be started. Make sure Chrome and ChromeDriver are installed."
        return "ok"

    def _reset_driver(self):
        """Force reset driver on critical failure."""
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
        self._driver = self._create_driver()
        return self._driver

    def open_url(self, url: str) -> str:
        status = self._ensure_driver()
        if status != "ok":
            return status
        
        url = url.strip()
        if not url:
            return "Please provide a URL."
        
        label = _url_to_label(url)
        normalized = _normalize_url(url)
        
        try:
            self._driver.get(normalized)
            self._last_url = normalized
            return f"{label} opened in browser."
        except Exception as e:
            # Try resetting driver and retry once
            if self._error_count < 2:
                logger.warning(f"Browser open failed, retrying with fresh driver...")
                self._reset_driver()
                try:
                    self._driver.get(normalized)
                    self._last_url = normalized
                    return f"{label} opened in browser."
                except Exception as e2:
                    return f"Failed to load URL: {str(e2)[:120]}"
            return f"Failed to load URL: {str(e)[:120]}"

    def click(self, selector: str) -> str:
        status = self._ensure_driver()
        if status != "ok":
            return status
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            el = WebDriverWait(self._driver, self.timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            el.click()
            return f"Element clicked successfully."
        except Exception as e:
            return f"Click failed: {str(e)[:120]}"

    def type_text(self, selector: str, text: str) -> str:
        status = self._ensure_driver()
        if status != "ok":
            return status
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            el = WebDriverWait(self._driver, self.timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            el.clear()
            el.send_keys(text)
            return f"Text entered successfully."
        except Exception as e:
            return f"Typing failed: {str(e)[:120]}"

    def scrape(self, url: str, query: str) -> str:
        """Open page and extract text matching query."""
        status = self._ensure_driver()
        if status != "ok":
            return status
        
        normalized = _normalize_url(url)
        try:
            self._driver.get(normalized)
            
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            WebDriverWait(self._driver, self.timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Try to extract structured text
            try:
                title = self._driver.title or ""
            except Exception:
                title = ""

            # Extract all visible text
            body_text = self._driver.find_element(By.TAG_NAME, "body").text
            lines = [l.strip() for l in body_text.split("\n") if l.strip() and len(l.strip()) > 5]

            # Filter by query if provided
            if query and query.strip():
                query_lower = query.lower().strip()
                matching = [l for l in lines if query_lower in l.lower()]
                if matching:
                    return f"🌐 {title}\n\n" + "\n".join(matching[:10])
            
            return f"🌐 {title}\n\n" + "\n".join(lines[:20])

        except Exception as e:
            return f"Scrape failed: {str(e)[:120]}"

    def get_current_url(self) -> str:
        """Get current page URL."""
        if self._driver:
            try:
                return self._driver.current_url
            except Exception:
                pass
        return ""

    def quit(self) -> str:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
        return "Browser closed."


# Singleton
_browser_agent: Optional[BrowserAgent] = None


def get_browser_agent() -> BrowserAgent:
    global _browser_agent
    if _browser_agent is None:
        _browser_agent = BrowserAgent()
    return _browser_agent
