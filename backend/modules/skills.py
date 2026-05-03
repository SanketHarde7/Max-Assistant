"""
Skills Engine Module v3.0 — FIXED
Central skill dispatcher for JARVIS.

ROOT CAUSE FIXES:
1. parse_and_execute made ASYNC → direct await, no asyncio.create_task() hack
2. _skill_X wrappers for code/file skills simplified → just return coroutine
3. asyncio.run() inside running loop removed entirely
4. youtube_search removed from DATA_SKILLS (it's an action, not data)
5. TTS truncation added for long results (find_and_explain, run_code, code_review)
"""

import re
import os
import time
import asyncio
import threading
import subprocess
import logging
import platform
import webbrowser
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger("JARVIS.SKILLS")

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    import pywhatkit
    PYWHATKIT_AVAILABLE = True
except ImportError:
    PYWHATKIT_AVAILABLE = False

# ═══════════════════════════════════════════════════
# DATA vs ACTION Skill Classification
#
# DATA  → result spoken by TTS
# ACTION → result NOT spoken (LLM already said what it's doing)
# Long DATA skills → truncated before TTS
# ═══════════════════════════════════════════════════

DATA_SKILLS = {
    "weather",          # short result → always speak
    "search",           # abstract → speak if short
    "note",             # "Note saved" → short, speak
    "timer",            # "Timer set for X" → short, speak
    "find_and_explain", # LLM explanation → TRUNCATE before TTS
    "list_files",       # listing → TRUNCATE
    "read_file",        # file content → TRUNCATE
    "code_review",      # review → TRUNCATE
    "run_code",         # output → TRUNCATE
    "search_files",     # results → TRUNCATE
}

LONG_RESULT_SKILLS = {
    "find_and_explain", "list_files", "read_file",
    "code_review", "run_code", "search_files"
}

TTS_MAX_CHARS = 280


def _truncate_for_tts(result: str, skill_name: str) -> str:
    """Truncate long skill results to TTS-safe length."""
    if skill_name not in LONG_RESULT_SKILLS:
        return result

    # Strip emoji header lines (e.g. "📄 main.py (12KB)\n\n")
    lines = result.split('\n')
    content_lines = [l for l in lines if l.strip() and not l.startswith(('📄', '📁', '🔍'))]
    joined = ' '.join(content_lines)

    if len(joined) <= TTS_MAX_CHARS:
        return joined

    truncated = joined[:TTS_MAX_CHARS]
    last_period = max(truncated.rfind('. '), truncated.rfind('! '), truncated.rfind('? '))
    if last_period > TTS_MAX_CHARS // 2:
        truncated = truncated[:last_period + 1]

    return f"{truncated} Details screen pe hain sir."


class SkillsEngine:
    """Central skill dispatcher — v3.0 with async dispatcher."""

    SKILL_PATTERN = re.compile(r'\[SKILL:([a-zA-Z_]+)(?::([^\]]*))?\]')

    def __init__(self, config):
        self.config = config
        self._code_engine = None
        self._file_manager = None
        self.skills_registry = self._register_skills()

    @property
    def code_engine(self):
        if self._code_engine is None:
            from modules.code_engine import get_code_engine
            self._code_engine = get_code_engine(self.config)
        return self._code_engine

    @property
    def file_manager(self):
        if self._file_manager is None:
            from modules.file_manager import get_file_manager
            self._file_manager = get_file_manager(self.config)
        return self._file_manager

    def _register_skills(self) -> Dict[str, callable]:
        return {
            "weather":          self._skill_weather,
            "timer":            self._skill_timer,
            "note":             self._skill_note,
            "search":           self._skill_web_search,
            "youtube_search":   self._skill_youtube_search,
            "clear_memory":     self._skill_clear_memory,
            "write_code":       self._skill_write_code,
            "run_code":         self._skill_run_code,
            "code_review":      self._skill_code_review,
            "fix_code":         self._skill_fix_code,
            "project_scaffold": self._skill_project_scaffold,
            "find_and_explain": self._skill_find_and_explain,
            "list_files":       self._skill_list_files,
            "read_file":        self._skill_read_file,
            "edit_file":        self._skill_edit_file,
            "search_files":     self._skill_search_files,
            "open_app":         self._skill_open_app,
            "web_open":         self._skill_web_open,
            "screenshot":       self._skill_screenshot,
            "volume":           self._skill_volume_control,
            "whatsapp_message": self._skill_whatsapp_message,
            "type_text":        self._skill_type_text,
            "system_shutdown":  self._skill_system_shutdown,
            "system_restart":   self._skill_system_restart,
        }

    # ═══════════════════════════════════════════
    # ASYNC DISPATCHER — CORE FIX
    # ═══════════════════════════════════════════

    async def parse_and_execute(self, response_text: str, memory_context: str = "") -> Dict[str, Any]:
        """
        Parse [SKILL:name:params] and execute.

        FIXED: Now async. Coroutines from code/file skills are directly awaited.
        No asyncio.create_task() (returns Task not result).
        No asyncio.run() (crashes inside running FastAPI loop).
        """
        match = self.SKILL_PATTERN.search(response_text)
        if not match:
            return {"executed": False, "clean_text": response_text, "is_data_skill": False}

        skill_name = match.group(1).lower()
        params_str = match.group(2) or ""
        params = [p.strip() for p in params_str.split(":") if p.strip()]

        clean_text = self.SKILL_PATTERN.sub("", response_text).strip()
        clean_text = re.sub(r' {2,}', ' ', clean_text)

        if skill_name not in self.skills_registry:
            logger.warning(f"Unknown skill: {skill_name}")
            return {"executed": False, "clean_text": clean_text, "is_data_skill": False}

        try:
            logger.info(f"Executing skill: {skill_name}({params})")
            raw = self.skills_registry[skill_name](*params)

            # Await if coroutine (code/file skills), else use directly (sync skills)
            if asyncio.iscoroutine(raw):
                result = await raw
            else:
                result = raw

            result_str = str(result) if result else ""
            tts_result = _truncate_for_tts(result_str, skill_name)

            return {
                "executed":      True,
                "skill_name":    skill_name,
                "params":        params,
                "result":        result_str,
                "tts_result":    tts_result,
                "clean_text":    clean_text,
                "is_data_skill": skill_name in DATA_SKILLS,
            }

        except Exception as e:
            import traceback
            logger.error(f"Skill '{skill_name}' failed: {e}\n{traceback.format_exc()}")
            return {
                "executed":      False,
                "error":         str(e),
                "clean_text":    clean_text,
                "is_data_skill": False,
            }

    # ═══════════════════════════════════════════
    # CODE SKILL WRAPPERS
    # Just return the coroutine — dispatcher awaits it
    # ═══════════════════════════════════════════

    def _skill_write_code(self, *args):
        return self.code_engine.write_code(*args)

    def _skill_run_code(self, *args):
        return self.code_engine.run_code(*args)

    def _skill_code_review(self, *args):
        return self.code_engine.code_review(*args)

    def _skill_fix_code(self, *args):
        return self.code_engine.fix_code(*args)

    def _skill_project_scaffold(self, *args):
        return self.code_engine.project_scaffold(*args)

    # ═══════════════════════════════════════════
    # FILE SKILL WRAPPERS
    # ═══════════════════════════════════════════

    def _skill_find_and_explain(self, *args):
        return self.file_manager.find_and_explain(*args)

    def _skill_list_files(self, *args):
        return self.file_manager.list_files(*args)

    def _skill_read_file(self, *args):
        return self.file_manager.read_file(*args)

    def _skill_edit_file(self, *args):
        return self.file_manager.edit_file(*args)

    def _skill_search_files(self, *args):
        return self.file_manager.search_files(*args)

    # ═══════════════════════════════════════════
    # CORE SKILLS
    # ═══════════════════════════════════════════

    def _skill_weather(self, city: str = "auto") -> str:
        try:
            import httpx
            city = city.strip() or "auto"
            url = f"https://wttr.in/{city}?format=3&lang=en"
            with httpx.Client(timeout=6.0) as client:
                resp = client.get(url, headers={"User-Agent": "curl/7.68.0"})
                if resp.status_code == 200:
                    return resp.text.strip()
            return f"Weather unavailable for {city}."
        except Exception as e:
            return "Unable to fetch weather sir."

    def _skill_timer(self, seconds: str = "60", label: str = "Timer") -> str:
        try:
            secs = int(seconds)
            if secs <= 0:
                return "Positive duration chahiye sir."

            def _countdown():
                time.sleep(secs)
                msg = f"JARVIS: {label} done! {secs}s elapsed."
                try:
                    from plyer import notification
                    notification.notify(title="JARVIS Timer", message=msg, timeout=8)
                    return
                except ImportError:
                    pass
                if PYAUTOGUI_AVAILABLE:
                    try:
                        pyautogui.alert(text=msg, title="JARVIS Timer", button="OK")
                        return
                    except Exception:
                        pass
                if platform.system() == "Windows":
                    try:
                        subprocess.run([
                            "powershell", "-Command",
                            f"Add-Type -AssemblyName System.Windows.Forms; "
                            f"[System.Windows.Forms.MessageBox]::Show('{msg}', 'JARVIS')"
                        ], capture_output=True)
                    except Exception:
                        pass

            threading.Thread(target=_countdown, daemon=True).start()
            mins, rem = divmod(secs, 60)
            return f"Timer set for {f'{mins}m {rem}s' if mins else f'{secs}s'} sir."
        except ValueError:
            return "Timer duration in seconds do sir."

    def _skill_note(self, *args) -> str:
        try:
            text = " ".join(args).strip()
            if not text:
                return "Kuch likhna toh padega sir."
            notes_file = Path(self.config.DATA_DIR) / "notes.txt"
            notes_file.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(notes_file, 'a', encoding='utf-8') as f:
                f.write(f"[{ts}] {text}\n")
            return "Note save ho gayi sir."
        except Exception as e:
            logger.error(f"Note error: {e}")
            return "Note save nahi ho payi sir."

    def _skill_web_search(self, *args) -> str:
        """
        Search web using Google News RSS first, then DuckDuckGo Instant Answer.

        Falls back to opening a browser only when both data sources fail.
        """
        import httpx
        import xml.etree.ElementTree as ET

        query = " ".join(args).strip()
        if not query:
            return "Kya search karna hai sir?"

        try:
            encoded_query = query.replace(" ", "+")
            rss_url = (
                f"https://news.google.com/rss/search"
                f"?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
            )
            with httpx.Client(timeout=7.0) as client:
                resp = client.get(rss_url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    items = root.findall('.//item')[:4]

                    if items:
                        headlines = []
                        for item in items:
                            title_el = item.find('title')
                            if title_el is not None and title_el.text:
                                title = title_el.text.strip()
                                if " - " in title:
                                    title = title.rsplit(" - ", 1)[0]
                                headlines.append(title)

                        if headlines:
                            if len(headlines) == 1:
                                return headlines[0]
                            return ". ".join(headlines[:3])

        except Exception as e:
            logger.warning(f"Google News RSS failed: {e}")

        try:
            params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
            with httpx.Client(timeout=5.0) as client:
                data = client.get("https://api.duckduckgo.com/", params=params).json()
                abstract = data.get("AbstractText", "").strip()
                if abstract:
                    return abstract[:300]
        except Exception:
            pass

        webbrowser.open(f"https://duckduckgo.com/?q={query.replace(' ', '+')}")
        return f"Search results browser mein khole sir '{query}' ke liye."

    def _skill_youtube_search(self, *args) -> str:
        query = " ".join(args).strip()
        if not query:
            return "YouTube pe kya search karu sir?"
        webbrowser.open(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}")
        return f"YouTube pe search kiya sir."

    def _skill_clear_memory(self) -> str:
        return "Memory clear ho gayi sir."

    # ═══════════════════════════════════════════
    # PC CONTROL SKILLS
    # ═══════════════════════════════════════════

    def _skill_open_app(self, app_name: str = "", **kwargs) -> str:
        if not app_name:
            return "Kaunsa app kholna hai sir?"
        system = platform.system()
        app_lower = app_name.lower().strip()
        windows_map = getattr(self.config, 'WINDOWS_APP_MAP', {})
        mac_map = getattr(self.config, 'MAC_APP_MAP', {})
        web_fallback = getattr(self.config, 'WEB_FALLBACK_MAP', {})

        try:
            if system == "Windows":
                cmd = windows_map.get(app_lower, app_lower)
                subprocess.Popen(cmd, shell=True)
                return f"{app_name} khol diya sir."
            elif system == "Darwin":
                subprocess.run(["open", "-a", mac_map.get(app_lower, app_name)], check=True)
                return f"{app_name} khol diya sir."
            else:
                subprocess.Popen([app_lower])
                return f"{app_name} khol diya sir."
        except Exception:
            logger.warning(f"Local open failed: '{app_name}'")

        fallback_url = web_fallback.get(app_lower, f"https://www.{app_lower.replace(' ', '')}.com")
        webbrowser.open(fallback_url)
        return f"{app_name} browser mein khola sir."

    def _skill_web_open(self, url: str = "", **kwargs) -> str:
        if not url:
            return "URL do sir."
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            webbrowser.open(url)
            return f"Browser mein khola sir."
        except Exception as e:
            return f"URL nahi khul paya: {e}"

    def _skill_screenshot(self, filename: str = "", **kwargs) -> str:
        if not PYAUTOGUI_AVAILABLE:
            return "Screenshot ke liye: pip install pyautogui"
        try:
            save_dir = Path(self.config.DATA_DIR) / "screenshots"
            save_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            base = filename.strip() or "jarvis_screenshot"
            filepath = save_dir / f"{base}_{ts}.png"
            pyautogui.screenshot(str(filepath))
            return f"Screenshot li sir: {filepath.name}"
        except Exception as e:
            return f"Screenshot failed: {e}"

    def _skill_volume_control(self, action: str = "up", value: str = "10", **kwargs) -> str:
        try:
            system = platform.system()
            action_lower = action.lower()
            if system == "Windows":
                try:
                    from ctypes import cast, POINTER
                    from comtypes import CLSCTX_ALL
                    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                    devices = AudioUtilities.GetSpeakers()
                    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    vol = cast(interface, POINTER(IAudioEndpointVolume))
                    step = int(value) / 100.0
                    if action_lower == "up":
                        vol.SetMasterVolumeLevelScalar(min(1.0, vol.GetMasterVolumeLevelScalar() + step), None)
                    elif action_lower == "down":
                        vol.SetMasterVolumeLevelScalar(max(0.0, vol.GetMasterVolumeLevelScalar() - step), None)
                    elif action_lower == "mute":
                        vol.SetMute(not vol.GetMute(), None)
                    elif action_lower == "set":
                        vol.SetMasterVolumeLevelScalar(min(1.0, int(value) / 100.0), None)
                    return f"Volume {action_lower} kar diya sir."
                except ImportError:
                    return "Volume ke liye: pip install pycaw"
            elif system == "Darwin":
                if action_lower == "mute":
                    subprocess.run(["osascript", "-e", "set volume output muted true"], check=True)
                else:
                    subprocess.run(["osascript", "-e", f"set volume output volume {max(0,min(100,int(value)))}"], check=True)
                return f"Volume adjust kar diya sir."
            else:
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{value}%"], check=True)
                return f"Volume {value}% sir."
        except Exception as e:
            return f"Volume control failed: {e}"

    def _skill_whatsapp_message(self, contact: str = "", message: str = "", **kwargs) -> str:
        if not PYWHATKIT_AVAILABLE:
            return "WhatsApp ke liye: pip install pywhatkit"
        if not contact:
            return "Contact number do sir."
        if not message:
            return "Message kya bhejna hai sir?"
        if not contact.startswith("+"):
            contact = "+" + contact
        try:
            pywhatkit.sendwhatmsg_instantly(phone_no=contact, message=message,
                                            wait_time=15, tab_close=True, close_time=3)
            return "WhatsApp message bhej diya sir."
        except Exception as e:
            return f"WhatsApp failed: {e}"

    def _skill_type_text(self, *args) -> str:
        if not PYAUTOGUI_AVAILABLE:
            return "Typing ke liye: pip install pyautogui"
        text = " ".join(args).strip()
        if not text:
            return "Kya type karu sir?"
        try:
            time.sleep(1.5)
            pyautogui.write(text, interval=0.04)
            return "Type kar diya sir."
        except Exception as e:
            return f"Typing failed: {e}"

    def _skill_system_shutdown(self, delay: str = "30", **kwargs) -> str:
        try:
            secs = max(0, int(delay))
            if platform.system() == "Windows":
                subprocess.run(["shutdown", "/s", "/t", str(secs)], check=True)
            else:
                subprocess.run(["sudo", "shutdown", "-h", f"+{max(1, secs//60)}"], check=True)
            return f"System {secs}s mein shutdown hoga sir."
        except Exception as e:
            return f"Shutdown failed: {e}"

    def _skill_system_restart(self, delay: str = "30", **kwargs) -> str:
        try:
            secs = max(0, int(delay))
            if platform.system() == "Windows":
                subprocess.run(["shutdown", "/r", "/t", str(secs)], check=True)
            else:
                subprocess.run(["sudo", "shutdown", "-r", f"+{max(1, secs//60)}"], check=True)
            return f"System {secs}s mein restart hoga sir."
        except Exception as e:
            return f"Restart failed: {e}"


_skills_instance: Optional[SkillsEngine] = None


def get_skills_engine(config) -> SkillsEngine:
    global _skills_instance
    if _skills_instance is None:
        _skills_instance = SkillsEngine(config)
    return _skills_instance
