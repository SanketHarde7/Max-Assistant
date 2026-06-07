# Path: backend/modules/ai_orchestrator/response_harvester.py
# Use: Retrieves and structures finalized model outputs.
# response_harvester.py — Waits for and reads AI assistant responses
import time
import logging
from selenium.webdriver.common.by import By
from modules.ai_orchestrator.platform_config import PlatformInfo

logger = logging.getLogger("MAX.ORCHESTRATOR.HARVESTER")

class ResponseHarvester:
    def __init__(self, driver, platform_info: PlatformInfo):
        self.driver = driver
        self.platform = platform_info

    def _get_latest_response_element(self):
        for selector in self.platform.response_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    return elements[-1]
            except Exception:
                continue
        return None

    def wait_for_response(self, timeout: int = 120) -> bool:
        start_time = time.time()
        last_text = ""
        stable_since = time.time()
        text_generated = False

        logger.info(f"Monitoring response stream with {self.platform.name} spec rules...")

        while time.time() - start_time < timeout:
            time.sleep(1.0)
            
            # 1. Check Platform-Specific Done Signals first
            # A. ChatGPT: Submit button is enabled (and not showing the stop button icon/state)
            if self.platform.response_done_signal == "send_button_enabled":
                try:
                    for selector in self.platform.submit_selectors:
                        btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                        # ChatGPT send button turns into stop icon (with specific aria-label or tag) during generation.
                        # If the button is enabled and has the prompt send attribute, we can say it's done.
                        if btn.is_enabled():
                            # Let's verify text is non-empty before finishing
                            elem = self._get_latest_response_element()
                            if elem and len(elem.text.strip()) > 10:
                                logger.info("Detected ChatGPT send button enabled. Done.")
                                return True
                except Exception:
                    pass

            # B. Gemini: Loading spinner is absent
            elif self.platform.response_done_signal == "spinner_gone":
                try:
                    # Gemini uses spinner tags or progress bars like 'mat-progress-bar', 'loading-spinner'
                    spinners = self.driver.find_elements(By.CSS_SELECTOR, "mat-progress-bar, .loading-spinner, .activity-indicator")
                    spinner_visible = any(s.is_displayed() for s in spinners)
                    if not spinner_visible:
                        elem = self._get_latest_response_element()
                        if elem and len(elem.text.strip()) > 10:
                            logger.info("Detected Gemini loading spinner disappeared. Done.")
                            return True
                except Exception:
                    pass

            # C. Perplexity: Sources/citations block is visible below response
            elif self.platform.response_done_signal == "sources_visible":
                try:
                    # Look for sources/citations section
                    sources = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Sources') or contains(@class, 'sources')]")
                    if sources:
                        elem = self._get_latest_response_element()
                        if elem and len(elem.text.strip()) > 10:
                            logger.info("Detected Perplexity sources list. Done.")
                            return True
                except Exception:
                    pass

            # 2. Universal Text Stabilization Check (Fallback & Primary for Claude)
            elem = self._get_latest_response_element()
            if elem:
                current_text = elem.text.strip()
                if len(current_text) > 0:
                    text_generated = True
                    
                if current_text != last_text:
                    last_text = current_text
                    stable_since = time.time()
                else:
                    # Text has not changed. Check stability duration
                    if text_generated and (time.time() - stable_since >= 2.5):
                        logger.info(f"Universal check: response text length has been stable for {time.time() - stable_since:.1f}s. Done.")
                        return True
            else:
                # Still waiting for response container to appear
                pass

        logger.warning(f"Response wait timed out after {timeout} seconds.")
        return False

    def harvest_response(self) -> str:
        elem = self._get_latest_response_element()
        if elem:
            try:
                # get innerText directly to preserve formatting/spacing
                text = elem.get_attribute("innerText")
                if not text:
                    text = elem.text
                return text.strip()
            except Exception as e:
                logger.error(f"Failed to read text from response element: {e}")
                return ""
        return ""
