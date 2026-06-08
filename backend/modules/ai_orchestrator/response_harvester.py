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
        self._min_response_length = 10  # Minimum chars to consider valid
        self._stability_duration = 3.0  # Seconds of no change to consider done
        self._poll_interval = 1.0

    def _get_latest_response_element(self):
        """Get the most recent response element from the page."""
        for selector in self.platform.response_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    # Return the last (most recent) element
                    return elements[-1]
            except Exception:
                continue
        return None

    def _count_response_elements(self) -> int:
        """Count total response elements on page."""
        total = 0
        for selector in self.platform.response_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                total += len(elements)
            except Exception:
                continue
        return total

    def _get_response_text(self, elem) -> str:
        """Safely extract text from response element."""
        if not elem:
            return ""
        try:
            # Try innerText first (more reliable)
            text = elem.get_attribute("innerText")
            if text and len(text.strip()) > 0:
                return text.strip()
        except Exception:
            pass
        try:
            # Fallback to .text property
            text = elem.text
            if text:
                return text.strip()
        except Exception:
            pass
        try:
            # Last resort: get HTML and strip tags
            html = elem.get_attribute("innerHTML")
            if html:
                import re
                text = re.sub(r'<[^>]+>', ' ', html)
                text = re.sub(r'\s+', ' ', text).strip()
                return text
        except Exception:
            pass
        return ""

    def _is_generating(self) -> bool:
        """Check if the AI is still generating a response."""
        signal = self.platform.response_done_signal

        if signal == "send_button_enabled":
            # ChatGPT: Check if stop button is visible (generating) or send button is visible (done)
            try:
                # Look for stop button (square icon during generation)
                stop_indicators = [
                    "button[aria-label='Stop streaming']",
                    "button[data-testid='stop-button']",
                    "button svg path[d*='M6 6h12v12H6z']",  # Stop square icon
                    "button.border-token-main-surface-tertiary"  # Stop button styling
                ]
                for sel in stop_indicators:
                    try:
                        elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        for elem in elems:
                            if elem.is_displayed():
                                return True  # Still generating
                    except Exception:
                        continue
                        
                # Check if send button is enabled (not the stop button)
                for sel in self.platform.submit_selectors:
                    try:
                        btn = self.driver.find_element(By.CSS_SELECTOR, sel)
                        if btn.is_enabled() and btn.is_displayed():
                            # Make sure it's not the stop button
                            aria_label = btn.get_attribute("aria-label") or ""
                            if "stop" not in aria_label.lower():
                                return False  # Done generating
                    except Exception:
                        continue
            except Exception:
                pass
                
        elif signal == "spinner_gone":
            # Gemini: Check for loading indicators
            try:
                spinner_selectors = [
                    "mat-progress-bar", ".loading-spinner", ".activity-indicator",
                    ".skeleton", ".shimmer", "[data-loading]",
                    "svg[class*='animate-spin']", ".animate-pulse"
                ]
                for sel in spinner_selectors:
                    try:
                        elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        for elem in elems:
                            if elem.is_displayed():
                                return True
                    except Exception:
                        continue
            except Exception:
                pass
                
        elif signal == "sources_visible":
            # Perplexity: Check for sources/citations
            try:
                source_selectors = [
                    "*[contains(text(), 'Sources')]",
                    ".sources",
                    "[data-testid='sources']",
                    ".citation-list"
                ]
                for sel in source_selectors:
                    try:
                        elems = self.driver.find_elements(By.XPATH if "contains" in sel else By.CSS_SELECTOR, sel)
                        if elems:
                            return False  # Sources visible = done
                    except Exception:
                        continue
            except Exception:
                pass
                
        elif signal == "text_stabilized":
            # Claude: Use text stabilization check (handled in main loop)
            pass

        return None  # Unknown state

    def wait_for_response(self, timeout: int = 120) -> bool:
        """
        Wait for AI response to complete.
        Returns True if response appears complete, False on timeout.
        """
        start_time = time.time()
        last_text = ""
        stable_since = time.time()
        text_generated = False
        last_element_count = 0
        empty_count = 0

        logger.info(f"Monitoring response stream for {self.platform.name}...")

        while time.time() - start_time < timeout:
            time.sleep(self._poll_interval)
            
            # Check if response element exists
            elem = self._get_latest_response_element()
            
            if elem:
                current_text = self._get_response_text(elem)
                current_len = len(current_text) if current_text else 0
                
                # Detect if any text has appeared
                if current_len > 0:
                    text_generated = True
                    
                # Track empty responses (might indicate error)
                if current_len == 0 and text_generated:
                    empty_count += 1
                    if empty_count > 5:
                        logger.warning("Response element exists but is empty repeatedly")
                        return False
                else:
                    empty_count = 0

                # Platform-specific generation check
                generating = self._is_generating()
                
                if generating is False and current_len > self._min_response_length:
                    # Platform signals done AND we have text
                    logger.info(f"Platform signals complete. Response length: {current_len}")
                    return True
                    
                if generating is True:
                    # Still generating, reset stability timer
                    last_text = current_text
                    stable_since = time.time()
                    continue

                # Universal text stabilization check (for Claude or as fallback)
                if current_text != last_text:
                    # Text is still changing
                    last_text = current_text
                    stable_since = time.time()
                else:
                    # Text hasn't changed
                    if text_generated and (time.time() - stable_since >= self._stability_duration):
                        if current_len > self._min_response_length:
                            logger.info(
                                f"Text stable for {self._stability_duration}s. "
                                f"Length: {current_len}. Done."
                            )
                            return True
                        elif current_len > 0:
                            # Short but stable response - might be complete
                            logger.info(f"Short but stable response ({current_len} chars). Done.")
                            return True
            else:
                # No response element yet - wait for it to appear
                if time.time() - start_time > 30 and not text_generated:
                    logger.warning("No response element appeared after 30s")
                    # Try refreshing selectors (page might have changed)
                    pass

        logger.warning(f"Response wait timed out after {timeout} seconds.")
        return False

    def harvest_response(self) -> str:
        """
        Extract the final response text.
        Tries multiple extraction methods for robustness.
        """
        # Try primary selectors
        elem = self._get_latest_response_element()
        if elem:
            text = self._get_response_text(elem)
            if text and len(text.strip()) > 2:
                logger.info(f"Harvested response: {len(text)} chars")
                return text

        # Fallback: try to get ALL response elements and concatenate
        all_texts = []
        for selector in self.platform.response_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements[-3:]:  # Last 3 responses
                    text = self._get_response_text(el)
                    if text and len(text) > 5:
                        all_texts.append(text)
            except Exception:
                continue
        
        if all_texts:
            # Return the longest (most likely the full response)
            best = max(all_texts, key=len)
            logger.info(f"Harvested response via fallback: {len(best)} chars")
            return best

        # Last resort: get page text
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            text = body.text
            if text and len(text) > 100:
                logger.warning("Using full body text as fallback")
                return text[:5000]  # Limit body text
        except Exception:
            pass

        logger.error("Failed to harvest any response text")
        return ""

    def harvest_all_responses(self) -> list:
        """Harvest all response elements on page (for multi-turn)."""
        responses = []
        for selector in self.platform.response_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    text = self._get_response_text(el)
                    if text and len(text) > 5:
                        responses.append(text)
            except Exception:
                continue
        return responses
