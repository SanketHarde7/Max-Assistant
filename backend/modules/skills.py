"""
skills.py — JARVIS v4.0
Fixed + Enhanced:
1. parse_and_execute method (was missing in Gemini version)
2. Made async — coroutines awaited correctly
3. Google News RSS for search (actual headlines, not browser)
4. All missing skills restored + NEW: email, calendar, browser, smarthome, clipboard, brightness, lock, plugin
5. DATA_SKILLS properly classified
6. Friendly tone — no 'sir' overload
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
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

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
# Skill Classification
# DATA  → result spoken via TTS
# ACTION → LLM already said what it's doing, no repeat
# LONG_RESULT → DATA but truncated before TTS
# ═══════════════════════════════════════════════════

DATA_SKILLS = {
    "weather", "search", "note", "timer",
    "find_and_explain", "list_files", "read_file",
    "code_review", "run_code", "search_files",
    "read_screen", "list_windows",
    "email_check", "calendar_today", "calendar_week",
    "browser_scrape", "plugin_list",
}

LONG_RESULT_SKILLS = {
    "find_and_explain", "list_files", "read_file",
    "code_review", "run_code", "search_files",
    "read_screen", "list_windows",
    "browser_scrape",
}

TTS_MAX_CHARS = 280


def _truncate_for_tts(result: str, skill_name: str) -> str:
    if skill_name not in LONG_RESULT_SKILLS:
        return result
    lines = result.split('\n')
    content = ' '.join(l for l in lines if l.strip() and not l.startswith(('📄', '📁', '🔍', '📸', '📧', '📅', '🌐', '🔌')))
    if len(content) <= TTS_MAX_CHARS:
        return content
    truncated = content[:TTS_MAX_CHARS]
    last = max(truncated.rfind('. '), truncated.rfind('! '), truncated.rfind('? '))
    if last > TTS_MAX_CHARS // 2:
        truncated = truncated[:last + 1]
    return f"{truncated} Details screen pe hain bhai."


class SkillsEngine:

    SKILL_PATTERN = re.compile(r'\[SKILL:([a-zA-Z_]+)(?::([^\]]*))?\]')

    def __init__(self, config):
        self.config = config
        self._code_engine = None
        self._file_manager = None
        self._email_agent = None
        self._calendar_agent = None
        self._browser_agent = None
        self._smarthome_agent = None
        self._plugin_loader = None
        self.skills_registry = self._register_skills()
        # Auto-load plugins on init
        self._load_plugins()

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

    @property
    def email_agent(self):
        if self._email_agent is None:
            from modules.email_agent import get_email_agent
            self._email_agent = get_email_agent()
        return self._email_agent

    @property
    def calendar_agent(self):
        if self._calendar_agent is None:
            from modules.calendar_agent import get_calendar_agent
            self._calendar_agent = get_calendar_agent()
        return self._calendar_agent

    @property
    def browser_agent(self):
        if self._browser_agent is None:
            from modules.browser_agent import get_browser_agent
            self._browser_agent = get_browser_agent()
        return self._browser_agent

    @property
    def smarthome_agent(self):
        if self._smarthome_agent is None:
            from modules.smarthome_agent import get_smarthome_agent
            self._smarthome_agent = get_smarthome_agent()
        return self._smarthome_agent

    @property
    def plugin_loader(self):
        if self._plugin_loader is None:
            from modules.plugin_loader import get_plugin_loader
            self._plugin_loader = get_plugin_loader()
        return self._plugin_loader

    def _load_plugins(self):
        try:
            self.plugin_loader.load_all()
        except Exception as e:
            logger.warning(f"Plugin loading failed: {e}")

    def _register_skills(self) -> Dict[str, Any]:
        base = {
            # Information
            "weather":          self._skill_weather,
            "timer":            self._skill_timer,
            "note":             self._skill_note,
            "search":           self._skill_web_search,
            "youtube_search":   self._skill_youtube_search,
            "clear_memory":     self._skill_clear_memory,
            "add_rule":         self._skill_add_rule,
            # Code
            "write_code":       self._skill_write_code,
            "run_code":         self._skill_run_code,
            "code_review":      self._skill_code_review,
            "fix_code":         self._skill_fix_code,
            "project_scaffold": self._skill_project_scaffold,
            # File
            "find_and_explain": self._skill_find_and_explain,
            "list_files":       self._skill_list_files,
            "read_file":        self._skill_read_file,
            "edit_file":        self._skill_edit_file,
            "search_files":     self._skill_search_files,
            # Screen / Vision
            "read_screen":      self._skill_read_screen,
            "list_windows":     self._skill_list_windows,
            "screenshot":       self._skill_screenshot,
            # PC Control
            "open_app":         self._skill_open_app,
            "web_open":         self._skill_web_open,
            "volume":           self._skill_volume_control,
            "whatsapp_message": self._skill_whatsapp_message,
            "type_text":        self._skill_type_text,
            "system_shutdown":  self._skill_system_shutdown,
            "system_restart":   self._skill_system_restart,
            # NEW PC Control
            "brightness":       self._skill_brightness,
            "clipboard":        self._skill_clipboard,
            "lock_pc":          self._skill_lock_pc,
            # Email
            "email_send":       self._skill_email_send,
            "email_check":      self._skill_email_check,
            # Calendar
            "calendar_today":   self._skill_calendar_today,
            "calendar_add":     self._skill_calendar_add,
            "calendar_week":    self._skill_calendar_week,
            # Browser
            "browser_open":     self._skill_browser_open,
            "browser_click":    self._skill_browser_click,
            "browser_type":     self._skill_browser_type,
            "browser_scrape":   self._skill_browser_scrape,
            # Smart Home
            "fan":              self._skill_fan,
            "smart_light":      self._skill_smart_light,
            "smart_ac":         self._skill_smart_ac,
            # Plugin
            "plugin_list":      self._skill_plugin_list,
            "plugin_reload":    self._skill_plugin_reload,
        }
        # Merge plugin skills dynamically
        try:
            pl = self.plugin_loader
            for name in pl.handlers:
                base[name] = lambda *args, n=name: pl.execute(n, *args)
        except Exception:
            pass
        return base

    # ═══════════════════════════════════════════
    # ASYNC DISPATCHER
    # ═══════════════════════════════════════════

    async def parse_and_execute(self, response_text: str, memory_context: str = "") -> Dict[str, Any]:
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
            logger.info(f"⚙️ Executing: {skill_name}({params})")
            raw = self.skills_registry[skill_name](*params)
            result = await raw if asyncio.iscoroutine(raw) else raw
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
            return {"executed": False, "error": str(e), "clean_text": clean_text, "is_data_skill": False}

    # ═══════════════════════════════════════════
    # CODE SKILL WRAPPERS
    # ═══════════════════════════════════════════

    def _skill_write_code(self, *args):       return self.code_engine.write_code(*args)
    def _skill_run_code(self, *args):         return self.code_engine.run_code(*args)
    def _skill_code_review(self, *args):      return self.code_engine.code_review(*args)
    def _skill_fix_code(self, *args):         return self.code_engine.fix_code(*args)
    def _skill_project_scaffold(self, *args): return self.code_engine.project_scaffold(*args)

    # ═══════════════════════════════════════════
    # FILE SKILL WRAPPERS
    # ═══════════════════════════════════════════

    def _skill_find_and_explain(self, *args): return self.file_manager.find_and_explain(*args)
    def _skill_list_files(self, *args):       return self.file_manager.list_files(*args)
    def _skill_read_file(self, *args):        return self.file_manager.read_file(*args)
    def _skill_edit_file(self, *args):        return self.file_manager.edit_file(*args)
    def _skill_search_files(self, *args):     return self.file_manager.search_files(*args)

    # ═══════════════════════════════════════════
    # INFORMATION SKILLS
    # ═══════════════════════════════════════════

    def _skill_weather(self, city: str = "auto") -> str:
        try:
            import httpx
            url = f"https://wttr.in/{city.strip() or 'auto'}?format=3&lang=en"
            with httpx.Client(timeout=7.0) as c:
                r = c.get(url, headers={"User-Agent": "curl/7.68.0"})
                return r.text.strip() if r.status_code == 200 else f"Weather unavailable for {city}."
        except Exception:
            return "Weather server se connect nahi ho paya bhai."

    def _skill_web_search(self, *args) -> str:
        import httpx
        query = " ".join(args).strip()
        if not query:
            return "Kya search karna hai bhai?"

        # ── Google News RSS — best for news/sports/current events ──
        try:
            encoded = query.replace(" ", "+")
            rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
            with httpx.Client(timeout=7.0) as c:
                resp = c.get(rss_url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    items = root.findall('.//item')[:4]
                    headlines = []
                    for item in items:
                        title_el = item.find('title')
                        if title_el is not None and title_el.text:
                            title = title_el.text.strip()
                            if " - " in title:
                                title = title.rsplit(" - ", 1)[0]
                            headlines.append(title)
                    if headlines:
                        return ". ".join(headlines[:3])
        except Exception as e:
            logger.warning(f"Google News RSS failed: {e}")

        # ── DuckDuckGo fallback ──
        try:
            params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
            with httpx.Client(timeout=5.0) as c:
                data = c.get("https://api.duckduckgo.com/", params=params).json()
                abstract = data.get("AbstractText", "").strip()
                if abstract:
                    return abstract[:300]
        except Exception:
            pass

        # ── Last resort: open browser ──
        webbrowser.open(f"https://duckduckgo.com/?q={query.replace(' ', '+')}")
        return f"Browser mein search khola bhai '{query}' ke liye."

    def _skill_youtube_search(self, *args) -> str:
        query = " ".join(args).strip()
        if not query:
            return "Kya search karna hai bhai YouTube pe?"
        webbrowser.open(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}")
        return f"YouTube search khola bhai."

    def _skill_clear_memory(self) -> str:
        return "Memory clear ho gayi bhai."

    def _skill_add_rule(self, *args) -> str:
        import json
        text = " ".join(args).strip()
        if not text:
            return "Rule text missing hai bhai."
        path = Path(self.config.DATA_DIR) / "permanent_rules.json"
        rules = json.loads(path.read_text()) if path.exists() else []
        rules.append({"rule": text, "timestamp": datetime.now().isoformat()})
        path.write_text(json.dumps(rules, indent=2))
        return f"Rule save ho gayi bhai."

    def _skill_timer(self, seconds: str = "60", label: str = "Timer") -> str:
        try:
            secs = int(seconds)
            if secs <= 0:
                return "Positive duration chahiye bhai."

            def _countdown():
                time.sleep(secs)
                msg = f"JARVIS: {label} khatam! {secs}s ho gaye."
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
                    subprocess.run([
                        "powershell", "-Command",
                        f"Add-Type -AssemblyName System.Windows.Forms; "
                        f"[System.Windows.Forms.MessageBox]::Show('{msg}','JARVIS')"
                    ], capture_output=True)

            threading.Thread(target=_countdown, daemon=True).start()
            mins, rem = divmod(secs, 60)
            return f"Timer set for {f'{mins}m {rem}s' if mins else f'{secs}s'} bhai."
        except ValueError:
            return "Seconds mein duration do bhai."

    def _skill_note(self, *args) -> str:
        try:
            text = " ".join(args).strip()
            if not text:
                return "Kuch likhna toh chahiye bhai note mein."
            notes_file = Path(self.config.DATA_DIR) / "notes.txt"
            notes_file.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(notes_file, 'a', encoding='utf-8') as f:
                f.write(f"[{ts}] {text}\n")
            return "Note save ho gayi bhai."
        except Exception as e:
            return f"Note save nahi ho payi: {e}"

    # ═══════════════════════════════════════════
    # SCREEN / VISION SKILLS
    # ═══════════════════════════════════════════

    async def _skill_read_screen(self, *args) -> str:
        target_name = " ".join(args).strip()
        try:
            import pyautogui as pg
            ss_dir = Path(self.config.DATA_DIR) / "screenshots"
            ss_dir.mkdir(parents=True, exist_ok=True)
            debug_path = ss_dir / "vision_debug.jpg"

            region = None
            if target_name and target_name.lower() != "all":
                try:
                    import pygetwindow as gw
                    wins = gw.getWindowsWithTitle(target_name)
                    if wins:
                        win = wins[0]
                        try:
                            win.activate()
                            time.sleep(0.7)
                        except Exception:
                            pass
                        region = (win.left, win.top, win.width, win.height)
                except ImportError:
                    logger.warning("pygetwindow not installed")

            pg.screenshot(region=region).convert('RGB').save(str(debug_path), quality=85)
            logger.info(f"Vision screenshot saved: {debug_path}")

            from modules.llm import analyze_image_with_prompt
            prompt = f"Identify what is open in the '{target_name or 'screen'}'. Read URLs and main text visible."
            return await analyze_image_with_prompt(str(debug_path), prompt)

        except ImportError:
            return "Screen read ke liye pyautogui install karo bhai."
        except Exception as e:
            return f"Screen read failed: {e}"

    def _skill_list_windows(self, *args) -> str:
        try:
            import pygetwindow as gw
            titles = [t for t in gw.getAllTitles() if t.strip()]
            if not titles:
                return "Koi active window nahi mili bhai."
            return "Open windows: " + ", ".join(titles[:10])
        except ImportError:
            return "pygetwindow install karo bhai: pip install pygetwindow"

    def _skill_screenshot(self, filename: str = "", **kwargs) -> str:
        if not PYAUTOGUI_AVAILABLE:
            return "Screenshot ke liye pyautogui install karo bhai."
        try:
            save_dir = Path(self.config.DATA_DIR) / "screenshots"
            save_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            base = filename.strip() or "jarvis_screenshot"
            filepath = save_dir / f"{base}_{ts}.png"
            pyautogui.screenshot(str(filepath))
            return f"Screenshot li bhai: {filepath.name}"
        except Exception as e:
            return f"Screenshot failed: {e}"

    # ═══════════════════════════════════════════
    # PC CONTROL SKILLS
    # ═══════════════════════════════════════════

    def _skill_open_app(self, app_name: str = "", **kwargs) -> str:
        if not app_name:
            return "Kaunsa app kholna hai bhai?"
        system = platform.system()
        app_lower = app_name.lower().strip()
        win_map = getattr(self.config, 'WINDOWS_APP_MAP', {})
        mac_map = getattr(self.config, 'MAC_APP_MAP', {})
        web_map = getattr(self.config, 'WEB_FALLBACK_MAP', {})

        try:
            if system == "Windows":
                cmd = win_map.get(app_lower, app_lower)
                subprocess.Popen(cmd, shell=True)
                return f"{app_name} khol diya bhai."
            elif system == "Darwin":
                subprocess.run(["open", "-a", mac_map.get(app_lower, app_name)], check=True)
                return f"{app_name} khol diya bhai."
            else:
                subprocess.Popen([app_lower])
                return f"{app_name} khol diya bhai."
        except Exception:
            logger.warning(f"Local open failed: '{app_name}'")

        fallback = web_map.get(app_lower, f"https://www.{app_lower.replace(' ','')}.com")
        webbrowser.open(fallback)
        return f"{app_name} locally nahi mila. Browser mein khola bhai."

    def _skill_web_open(self, url: str = "", **kwargs) -> str:
        if not url:
            return "URL do bhai."
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            webbrowser.open(url)
            return f"Browser mein khola bhai."
        except Exception as e:
            return f"URL nahi khul paya: {e}"

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
                    return f"Volume {action_lower} kar diya bhai."
                except ImportError:
                    return "Volume ke liye: pip install pycaw"
            elif system == "Darwin":
                if action_lower == "mute":
                    subprocess.run(["osascript", "-e", "set volume output muted true"])
                else:
                    subprocess.run(["osascript", "-e", f"set volume output volume {max(0,min(100,int(value)))}"])
                return "Volume adjust kar diya bhai."
            else:
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{value}%"])
                return f"Volume {value}% bhai."
        except Exception as e:
            return f"Volume control failed: {e}"

    def _skill_whatsapp_message(self, contact: str = "", message: str = "", **kwargs) -> str:
        if not PYWHATKIT_AVAILABLE:
            return "WhatsApp ke liye: pip install pywhatkit"
        if not contact:
            return "Contact number do bhai (+91 format)."
        if not message:
            return "Message kya bhejna hai bhai?"
        if not contact.startswith("+"):
            contact = "+" + contact
        try:
            pywhatkit.sendwhatmsg_instantly(phone_no=contact, message=message,
                                            wait_time=15, tab_close=True, close_time=3)
            return "WhatsApp message bhej diya bhai."
        except Exception as e:
            return f"WhatsApp failed: {e}"

    def _skill_type_text(self, *args) -> str:
        if not PYAUTOGUI_AVAILABLE:
            return "Typing ke liye: pip install pyautogui"
        text = " ".join(args).strip()
        if not text:
            return "Kya type karu bhai?"
        try:
            time.sleep(1.5)
            pyautogui.write(text, interval=0.04)
            return "Type kar diya bhai."
        except Exception as e:
            return f"Typing failed: {e}"

    def _skill_system_shutdown(self, delay: str = "30", **kwargs) -> str:
        try:
            secs = max(0, int(delay))
            if platform.system() == "Windows":
                subprocess.run(["shutdown", "/s", "/t", str(secs)], check=True)
            else:
                subprocess.run(["sudo", "shutdown", "-h", f"+{max(1,secs//60)}"], check=True)
            return f"System {secs}s mein shutdown hoga bhai. Save kar lo."
        except Exception as e:
            return f"Shutdown failed: {e}"

    def _skill_system_restart(self, delay: str = "30", **kwargs) -> str:
        try:
            secs = max(0, int(delay))
            if platform.system() == "Windows":
                subprocess.run(["shutdown", "/r", "/t", str(secs)], check=True)
            else:
                subprocess.run(["sudo", "shutdown", "-r", f"+{max(1,secs//60)}"], check=True)
            return f"System {secs}s mein restart hoga bhai."
        except Exception as e:
            return f"Restart failed: {e}"

    # ═══════════════════════════════════════════
    # NEW PC CONTROL SKILLS
    # ═══════════════════════════════════════════

    def _skill_brightness(self, action: str = "up", value: str = "10") -> str:
        try:
            system = platform.system()
            if system == "Windows":
                try:
                    import wmi
                    w = wmi.WMI(namespace='wmi')
                    methods = w.WmiMonitorBrightnessMethods()[0]
                    current = w.WmiMonitorBrightness()[0].CurrentBrightness
                    step = int(value)
                    if action.lower() == "up":
                        new_val = min(100, current + step)
                    elif action.lower() == "down":
                        new_val = max(0, current - step)
                    else:
                        new_val = max(0, min(100, int(value)))
                    methods.WmiSetBrightness(new_val, 0)
                    return f"Brightness {new_val}% kar diya bhai."
                except ImportError:
                    return "Brightness ke liye: pip install wmi pywin32"
            elif system == "Darwin":
                # macOS brightness control via brightness CLI or osascript
                subprocess.run(["osascript", "-e", f"tell application \"System Events\" to key code 144"])
                return "Brightness adjust kar diya bhai."
            else:
                subprocess.run(["brightnessctl", "set", f"{value}%"])
                return f"Brightness {value}% bhai."
        except Exception as e:
            return f"Brightness control failed: {str(e)[:120]}"

    def _skill_clipboard(self, action: str = "get", text: str = "") -> str:
        try:
            import pyperclip
            if action.lower() == "get":
                content = pyperclip.paste()
                return f"Clipboard mein: {content[:200]}" if content else "Clipboard khali hai bhai."
            elif action.lower() == "set":
                if not text:
                    return "Kya clipboard mein daalna hai bhai?"
                pyperclip.copy(text)
                return "Clipboard mein copy ho gaya bhai."
            else:
                return "Action 'get' ya 'set' do bhai."
        except ImportError:
            return "Clipboard ke liye: pip install pyperclip"
        except Exception as e:
            return f"Clipboard error: {str(e)[:120]}"

    def _skill_lock_pc(self, *args) -> str:
        try:
            system = platform.system()
            if system == "Windows":
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
            elif system == "Darwin":
                subprocess.run(["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"])
            else:
                subprocess.run(["gnome-screensaver-command", "-l"])
                # or loginctl lock-session
            return "System lock kar diya bhai."
        except Exception as e:
            return f"Lock nahi ho paya: {str(e)[:120]}"

    # ═══════════════════════════════════════════
    # EMAIL SKILLS
    # ═══════════════════════════════════════════

    def _skill_email_send(self, to: str = "", subject: str = "", body: str = "") -> str:
        return self.email_agent.send_email(to, subject, body)

    def _skill_email_check(self, *args) -> str:
        return self.email_agent.check_emails()

    # ═══════════════════════════════════════════
    # CALENDAR SKILLS
    # ═══════════════════════════════════════════

    def _skill_calendar_today(self, *args) -> str:
        return self.calendar_agent.today()

    def _skill_calendar_add(self, *args) -> str:
        if len(args) < 2:
            return "Usage: calendar_add:title:date:time bhai."
        title = args[0]
        date = args[1]
        time_str = args[2] if len(args) > 2 else ""
        return self.calendar_agent.add_event(title, date, time_str)

    def _skill_calendar_week(self, *args) -> str:
        return self.calendar_agent.week()

    # ═══════════════════════════════════════════
    # BROWSER SKILLS
    # ═══════════════════════════════════════════

    def _skill_browser_open(self, *args) -> str:
        url = args[0] if args else ""
        return self.browser_agent.open_url(url)

    def _skill_browser_click(self, *args) -> str:
        selector = args[0] if args else ""
        return self.browser_agent.click(selector)

    def _skill_browser_type(self, *args) -> str:
        if len(args) < 2:
            return "Usage: browser_type:selector:text bhai."
        return self.browser_agent.type_text(args[0], args[1])

    def _skill_browser_scrape(self, *args) -> str:
        if len(args) < 2:
            return "Usage: browser_scrape:url:query bhai."
        return self.browser_agent.scrape(args[0], args[1])

    # ═══════════════════════════════════════════
    # SMART HOME SKILLS
    # ═══════════════════════════════════════════

    def _skill_fan(self, *args) -> str:
        action = args[0] if args else "on"
        value = args[1] if len(args) > 1 else ""
        return self.smarthome_agent.fan_control(action, value)

    def _skill_smart_light(self, *args) -> str:
        action = args[0] if args else "on"
        value = args[1] if len(args) > 1 else ""
        return self.smarthome_agent.light_control(action, value)

    def _skill_smart_ac(self, *args) -> str:
        action = args[0] if args else "on"
        value = args[1] if len(args) > 1 else ""
        return self.smarthome_agent.ac_control(action, value)

    # ═══════════════════════════════════════════
    # PLUGIN SKILLS
    # ═══════════════════════════════════════════

    def _skill_plugin_list(self, *args) -> str:
        return self.plugin_loader.list_plugins()

    def _skill_plugin_reload(self, *args) -> str:
        self.plugin_loader.reload()
        # Refresh registry
        self.skills_registry = self._register_skills()
        return "Plugins reload ho gaye bhai."


# ═══════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════

_skills_instance: Optional[SkillsEngine] = None


def get_skills_engine(config) -> SkillsEngine:
    global _skills_instance
    if _skills_instance is None:
        _skills_instance = SkillsEngine(config)
    return _skills_instance
