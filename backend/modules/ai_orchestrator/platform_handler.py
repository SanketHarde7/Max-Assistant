# Path: backend/modules/ai_orchestrator/platform_handler.py
# Use: Executes tasks on designated platform integrations.
# platform_handler.py — Selenium driver wrapper for AI Orchestrator using Opera
import os
import time
import logging
import platform as os_platform
import pyperclip
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from modules.ai_orchestrator.platform_config import PlatformInfo, PLATFORMS

logger = logging.getLogger("MAX.ORCHESTRATOR.HANDLER")

class AIOrchestratorDriver:
    _instance = None
    _profile_path = None
    _binary_path = None

    @classmethod
    def get_driver(cls, profile_path: str = None, binary_path: str = None):
        if cls._instance is None:
            cls._profile_path = profile_path
            cls._binary_path = binary_path
            cls._instance = cls._create_driver(profile_path, binary_path)
        else:
            # Check if driver is still alive
            try:
                cls._instance.title
            except Exception:
                logger.info("Existing Opera driver session dead. Creating new instance...")
                cls._instance = cls._create_driver(cls._profile_path, cls._binary_path)
        return cls._instance

    @classmethod
    def _create_driver(cls, profile_path: str = None, binary_path: str = None):
        options = uc.ChromeOptions()
        
        # Disable automation flag to bypass cloudflare/bot checks
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--start-minimized")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        if binary_path and os.path.exists(binary_path):
            logger.info(f"Using Opera binary at: {binary_path}")
            options.binary_location = binary_path
        else:
            logger.warning(f"Opera binary not found at {binary_path}. Falling back to default undetected_chromedriver binary logic.")
        
        if profile_path and os.path.exists(profile_path):
            logger.info(f"Using Opera profile at: {profile_path}")
            options.add_argument(f"--user-data-dir={profile_path}")
            # Opera typically uses "Default" or no specific profile directory argument, but this is safe
            options.add_argument("--profile-directory=Default")
            
        options.page_load_strategy = 'eager'
        
        try:
            kwargs = {"options": options}
            if binary_path and os.path.exists(binary_path):
                kwargs["browser_executable_path"] = binary_path
                # Hardcoding version_main=147 to fix Opera version mismatch and prevent ConnectionResetError
                kwargs["version_main"] = 147
                
            driver = uc.Chrome(**kwargs)
            driver.set_page_load_timeout(30)
            return driver
        except Exception as e:
            logger.error(f"Opera launch failed completely: {e}")
            raise e

    @classmethod
    def close_driver(cls):
        if cls._instance:
            try:
                cls._instance.quit()
            except Exception:
                pass
            cls._instance = None


class PlatformHandler:
    def __init__(self, config):
        self.config = config

    def execute_query(self, platform_name: str, prompt_data: dict) -> str:
        """
        Executes query on the specified platform synchronously (should be wrapped in to_thread).
        """
        platform_info = PLATFORMS.get(platform_name.lower())
        if not platform_info:
            raise ValueError(f"Unknown platform: {platform_name}")

        opera_profile = getattr(self.config, 'OPERA_PROFILE_PATH', None)
        opera_binary = getattr(self.config, 'OPERA_BINARY_PATH', None)
        driver = AIOrchestratorDriver.get_driver(opera_profile, opera_binary)

        # 1. Open Platform URL
        logger.info(f"Navigating to {platform_info.name} URL: {platform_info.url_new_chat}")
        driver.get(platform_info.url_new_chat)
        time.sleep(3.0)

        # Cloudflare / bot verification check
        page_title = driver.title.lower() if driver.title else ""
        if any(kw in page_title for kw in ["just a moment", "cloudflare", "checking your browser"]):
            logger.info("Cloudflare challenge page detected, waiting for automatic bypass...")
            for _ in range(6):
                time.sleep(2.5)
                updated_title = driver.title.lower() if driver.title else ""
                if not any(kw in updated_title for kw in ["just a moment", "cloudflare", "checking your browser"]):
                    logger.info("Bypassed Cloudflare check successfully.")
                    break

        chunks = prompt_data.get("chunks", [""])
        image_path = prompt_data.get("image_path")
        is_chunked = prompt_data.get("is_chunked", False)

        from modules.ai_orchestrator.response_harvester import ResponseHarvester
        harvester = ResponseHarvester(driver, platform_info)

        # 2. Inject chunks sequentially
        final_response = ""
        for idx, chunk in enumerate(chunks):
            # Locate Textarea
            textarea = None
            for selector in platform_info.textarea_selectors:
                try:
                    textarea = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    break
                except Exception:
                    continue
            
            if not textarea:
                raise Exception(f"Failed to find prompt input textarea on {platform_info.name}.")

            # Focus and clear the textarea
            textarea.click()
            time.sleep(0.3)
            control_key = Keys.COMMAND if os_platform.system() == "Darwin" else Keys.CONTROL
            textarea.send_keys(control_key, 'a')
            textarea.send_keys(Keys.BACKSPACE)
            time.sleep(0.2)

            # Send prompt text
            current_prompt = chunk
            if is_chunked:
                if idx < len(chunks) - 1:
                    current_prompt = f"This is part {idx+1}/{len(chunks)} of my request. Please reply ONLY with 'Received part {idx+1}' and do NOT process yet.\n\n{chunk}"
                else:
                    current_prompt = f"This is the final part {idx+1}/{len(chunks)} of my request. Now process all parts together.\n\n{chunk}"

            logger.info(f"Injecting prompt chunk {idx+1}/{len(chunks)} ({len(current_prompt)} chars)")
            if len(current_prompt) < 1000:
                textarea.send_keys(current_prompt)
            else:
                pyperclip.copy(current_prompt)
                textarea.send_keys(control_key, 'v')
            time.sleep(0.5)

            # Upload image/screenshot on the final chunk if supported
            if image_path and idx == len(chunks) - 1 and platform_info.supports_image:
                try:
                    logger.info(f"Uploading file: {image_path}")
                    file_input = driver.find_element(By.XPATH, "//input[@type='file']")
                    file_input.send_keys(image_path)
                    time.sleep(2.5)  # Wait for upload preview
                except Exception as e:
                    logger.warning(f"Failed to upload image directly: {e}. Will proceed without image upload.")

            # Submit prompt
            submitted = False
            for selector in platform_info.submit_selectors:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, selector)
                    if btn.is_enabled():
                        btn.click()
                        logger.info(f"Clicked submit button: {selector}")
                        submitted = True
                        break
                except Exception:
                    continue

            if not submitted:
                logger.info("Submit button not found or disabled. Fallback sending ENTER key...")
                textarea.send_keys(Keys.ENTER)

            time.sleep(1.5)  # Let submit register

            # Wait for response chunk to finish
            logger.info("Waiting for platform response to finish streaming...")
            timeout = getattr(self.config, 'AI_RESPONSE_TIMEOUT', 120)
            success = harvester.wait_for_response(timeout=timeout)
            
            if not success:
                logger.warning("Timeout waiting for response to complete.")

            # Retrieve final response text
            if idx == len(chunks) - 1:
                final_response = harvester.harvest_response()
            else:
                time.sleep(1.0)

        # Cleanup
        if not getattr(self.config, 'AI_KEEP_BROWSER_OPEN', True):
            AIOrchestratorDriver.close_driver()

        return final_response
