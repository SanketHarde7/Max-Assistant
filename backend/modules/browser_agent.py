"""
browser_agent.py — JARVIS v4.0
Selenium-based browser automation. Zero cost with webdriver-manager.
Skills: browser_open, browser_click, browser_type, browser_scrape
"""
import logging
import asyncio
from typing import Optional, Dict, Any
from config import config

logger = logging.getLogger("JARVIS.BROWSER")


class BrowserAgent:
    """Lightweight Selenium browser agent."""

    def __init__(self):
        self._driver = None
        self.headless = config.BROWSER_HEADLESS
        self.timeout = config.BROWSER_TIMEOUT

    def _get_driver(self):
        if self._driver is None:
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.service import Service
                from webdriver_manager.chrome import ChromeDriverManager
                from selenium.webdriver.chrome.options import Options

                options = Options()
                if self.headless:
                    options.add_argument("--headless")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")
                options.add_argument("--window-size=1920,1080")
                options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

                service = Service(ChromeDriverManager().install())
                self._driver = webdriver.Chrome(service=service, options=options)
                self._driver.set_page_load_timeout(self.timeout)
            except Exception as e:
                logger.error(f"Browser init failed: {e}")
                return None
        return self._driver

    def _ensure_driver(self) -> str:
        d = self._get_driver()
        if d is None:
            return "Browser start nahi ho paya bhai. Selenium install hai? 'pip install selenium webdriver-manager'"
        return "ok"

    def open_url(self, url: str) -> str:
        status = self._ensure_driver()
        if status != "ok":
            return status
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            self._driver.get(url)
            return f"Browser mein khola bhai: {url}"
        except Exception as e:
            return f"URL load nahi ho paya: {str(e)[:120]}"

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
            return f"Element click ho gaya bhai."
        except Exception as e:
            return f"Click nahi ho paya: {str(e)[:120]}"

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
            return f"Type kar diya bhai."
        except Exception as e:
            return f"Type nahi ho paya: {str(e)[:120]}"

    def scrape(self, url: str, query: str) -> str:
        """Open page and extract text matching query."""
        status = self._ensure_driver()
        if status != "ok":
            return status
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            self._driver.get(url)
            # Wait for body
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            WebDriverWait(self._driver, self.timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Try to extract structured text
            try:
                title = self._driver.title
            except Exception:
                title = ""

            # Extract all visible text
            body_text = self._driver.find_element(By.TAG_NAME, "body").text
            lines = [l.strip() for l in body_text.split("\n") if l.strip() and len(l.strip()) > 5]

            # Filter by query if provided
            query_lower = query.lower()
            matching = [l for l in lines if query_lower in l.lower()]
            if matching:
                return f"🌐 {title}\n\n" + "\n".join(matching[:8])
            else:
                return f"🌐 {title}\n\n" + "\n".join(lines[:15])

        except Exception as e:
            return f"Scrape nahi ho paya: {str(e)[:120]}"

    def quit(self) -> str:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
        return "Browser band kar diya bhai."


# Singleton
_browser_agent: Optional[BrowserAgent] = None


def get_browser_agent() -> BrowserAgent:
    global _browser_agent
    if _browser_agent is None:
        _browser_agent = BrowserAgent()
    return _browser_agent
