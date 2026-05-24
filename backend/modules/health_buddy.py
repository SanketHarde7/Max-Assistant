"""
health_buddy.py — MAX v4.7 (Health & Focus Agent)
- Runs a background thread tracking developer screen time.
- Triggers non-intrusive TTS audio responses without UI toast or pop-ups.
- Automatically resets on system idle/sleep.
"""
import time
import logging
import threading
from datetime import datetime

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

logger = logging.getLogger("MAX.HEALTH")

class HealthBuddy:
    def __init__(self, api_send_func):
        """
        api_send_func: Callback function to push messages/audio to the frontend websocket.
        """
        self.send_to_frontend = api_send_func
        self.running = False
        self.last_activity_time = time.time()
        self.last_mouse_pos = (0, 0)
        
        # Timers in seconds
        self.EYE_INTERVAL = 45 * 60     # 45 minutes
        self.POSTURE_INTERVAL = 90 * 60 # 90 minutes
        
        self.eye_timer = 0
        self.posture_timer = 0
        self.tick_rate = 5 # Check system state every 5 seconds

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._health_loop, daemon=True)
            self.thread.start()
            logger.info("MAX Health Focus Buddy active in background.")

    def stop(self):
        self.running = False

    def _check_system_idle(self) -> bool:
        """Checks if the user is away from PC to avoid fake ghost timers."""
        if not PYAUTOGUI_AVAILABLE:
            return False
            
        try:
            current_pos = pyautogui.position()
            if current_pos != self.last_mouse_pos:
                self.last_mouse_pos = current_pos
                self.last_activity_time = time.time()
                return False
            
            # If no mouse movement for more than 15 minutes, user is idle
            if time.time() - self.last_activity_time > 15 * 60:
                return True
        except Exception:
            pass
        return False

    def _health_loop(self):
        while self.running:
            time.sleep(self.tick_rate)
            
            # 1. Check if user is away or PC went to sleep
            if self._check_system_idle():
                # Reset timers if user takes a break automatically
                if self.eye_timer > 0 or self.posture_timer > 0:
                    logger.info("User is idle. Resetting health trackers.")
                    self.eye_timer = 0
                    self.posture_timer = 0
                continue
                
            # 2. Increment active tracking timers
            self.eye_timer += self.tick_rate
            self.posture_timer += self.tick_rate
            
            # 3. Eye Strain Check (45 Mins)
            if self.eye_timer >= self.EYE_INTERVAL:
                self._trigger_voice_alert(
                    text="Sanket, forty-five minutes passed. Look away from the screen for twenty seconds.",
                    reason="eye_strain"
                )
                self.eye_timer = 0 # Reset eye tracker
                
            # 4. Posture Check (90 Mins)
            if self.posture_timer >= self.POSTURE_INTERVAL:
                self._trigger_voice_alert(
                    text="Time to stretch. Roll your shoulders back and sit up straight.",
                    reason="posture"
                )
                self.posture_timer = 0 # Reset posture tracker

    def _trigger_voice_alert(self, text: str, reason: str):
        """Generates dynamic local audio response through MAX text-to-speech pipeline."""
        logger.info(f"Triggering soft voice reminder for: {reason}")
        try:
            # We bypass UI toasts completely by packaging the event directly as a pure audio stream request
            # This triggers useVoice / playAudio stream without text manipulation hooks
            from modules.tts import generate_tts # Assuming you have a standard local/cloud tts module
            
            # Generate speech data
            audio_base64 = generate_tts(text)
            
            if audio_base64:
                payload = {
                    "event": "audio_response",
                    "audio": audio_base64,
                    "metadata": {"type": "health_alert", "reason": reason}
                }
                # Pushes the audio directly to your active websocket connection loop
                self.send_to_frontend(payload)
        except Exception as e:
            logger.error(f"Failed to generate health voice payload: {e}")