"""
skills.py — MAX v4.2
New skills added:
  - sysinfo          → CPU, RAM, disk, battery
  - media            → play, pause, next, prev, stop
  - reminder_set     → [SKILL:reminder_set:text:YYYY-MM-DD:HH:MM]
  - reminder_list    → list pending reminders
  - reminder_clear   → clear all reminders
  - top_processes    → top CPU processes
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

logger = logging.getLogger("MAX.SKILLS")

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

DATA_SKILLS = {
    "weather", "search", "note", "timer", "time_now", "date_today",
    "find_and_explain", "list_files", "read_file",
    "code_review", "run_code", "search_files",
    "read_screen", "list_windows",
    "email_check", "calendar_today", "calendar_week",
    "browser_scrape", "plugin_list", "list_apps",
    "sysinfo", "top_processes", "reminder_list",
    "kb_search", "kb_list", "kb_stats", "kb_rebuild",}

LONG_RESULT_SKILLS = {
    "find_and_explain", "list_files", "read_file",
    "code_review", "run_code", "search_files",
    "read_screen", "list_windows", "browser_scrape",
    "list_apps", "top_processes",
}

TTS_MAX_CHARS = 280


def _truncate_for_tts(result: str, skill_name: str) -> str:
    if skill_name not in LONG_RESULT_SKILLS:
        return result
    lines = result.split('\n')
    content = ' '.join(l for l in lines if l.strip() and not l.startswith(
        ('📄', '📁', '🔍', '📸', '📧', '📅', '🌐', '🔌')))
    if len(content) <= TTS_MAX_CHARS:
        return content
    truncated = content[:TTS_MAX_CHARS]
    last = max(truncated.rfind('. '), truncated.rfind('! '), truncated.rfind('? '))
    if last > TTS_MAX_CHARS // 2:
        truncated = truncated[:last + 1]
    return f"{truncated} Details on screen."


class SkillsEngine:

    SKILL_PATTERN = re.compile(r'\[SKILL:([a-zA-Z_]+)(?::([^\]]*))?\]')

    def __init__(self, config):
        self.config = config
        self._code_engine    = None
        self._file_manager   = None
        self._email_agent    = None
        self._calendar_agent = None
        self._browser_agent  = None
        self._smarthome_agent= None
        self._plugin_loader  = None
        self._app_indexer    = None
        self.skills_registry = self._register_skills()
        self._load_plugins()

    # ── Lazy properties ──────────────────────────────────────

    @property
    def code_engine(self):
        if not self._code_engine:
            from modules.code_engine import get_code_engine
            self._code_engine = get_code_engine(self.config)
        return self._code_engine

    @property
    def file_manager(self):
        if not self._file_manager:
            from modules.file_manager import get_file_manager
            self._file_manager = get_file_manager(self.config)
        return self._file_manager

    @property
    def email_agent(self):
        if not self._email_agent:
            from modules.email_agent import get_email_agent
            self._email_agent = get_email_agent()
        return self._email_agent

    @property
    def calendar_agent(self):
        if not self._calendar_agent:
            from modules.calendar_agent import get_calendar_agent
            self._calendar_agent = get_calendar_agent()
        return self._calendar_agent

    @property
    def browser_agent(self):
        if not self._browser_agent:
            from modules.browser_agent import get_browser_agent
            self._browser_agent = get_browser_agent()
        return self._browser_agent

    @property
    def smarthome_agent(self):
        if not self._smarthome_agent:
            from modules.smarthome_agent import get_smarthome_agent
            self._smarthome_agent = get_smarthome_agent()
        return self._smarthome_agent

    @property
    def plugin_loader(self):
        if not self._plugin_loader:
            from modules.plugin_loader import get_plugin_loader
            self._plugin_loader = get_plugin_loader()
        return self._plugin_loader

    @property
    def app_indexer(self):
        if not self._app_indexer:
            from modules.app_indexer import get_app_indexer
            self._app_indexer = get_app_indexer(self.config)
        return self._app_indexer

    def _load_plugins(self):
        try:
            self.plugin_loader.load_all()
        except Exception as e:
            logger.warning(f"Plugin load failed: {e}")

    def _register_skills(self) -> Dict[str, Any]:
        base = {
            # Information
            "weather":           self._skill_weather,
            "timer":             self._skill_timer,
            "note":              self._skill_note,
            "search":            self._skill_web_search,
            "youtube_search":    self._skill_youtube_search,
            "youtube_play":      self._skill_youtube_play,
            "time_now":          self._skill_time_now,
            "date_today":        self._skill_date_today,
            "clear_memory":      self._skill_clear_memory,
            "add_rule":          self._skill_add_rule,
            # System
            "sysinfo":           self._skill_sysinfo,
            "top_processes":     self._skill_top_processes,
            # Media
            "media":             self._skill_media,
            # Reminders
            "reminder_set":      self._skill_reminder_set,
            "reminder_list":     self._skill_reminder_list,
            "reminder_clear":    self._skill_reminder_clear,
            # Code
            "write_code":        self._skill_write_code,
            "run_code":          self._skill_run_code,
            "code_review":       self._skill_code_review,
            "fix_code":          self._skill_fix_code,
            "project_scaffold":  self._skill_project_scaffold,
            # File
            "find_and_explain":  self._skill_find_and_explain,
            "list_files":        self._skill_list_files,
            "read_file":         self._skill_read_file,
            "edit_file":         self._skill_edit_file,
            "search_files":      self._skill_search_files,
            # Screen
            "read_screen":       self._skill_read_screen,
            "list_windows":      self._skill_list_windows,
            "screenshot":        self._skill_screenshot,
            # PC Control
            "open_app":          self._skill_open_app,
            "list_apps":         self._skill_list_apps,
            "rebuild_app_index": self._skill_rebuild_app_index,
            "web_open":          self._skill_web_open,
            "volume":            self._skill_volume_control,
            "brightness":        self._skill_brightness,
            "clipboard":         self._skill_clipboard,
            "lock_pc":           self._skill_lock_pc,
            "system_shutdown":   self._skill_system_shutdown,
            "system_restart":    self._skill_system_restart,
            "whatsapp_message":  self._skill_whatsapp_message,
            "type_text":         self._skill_type_text,
            # Email
            "email_send":        self._skill_email_send,
            "email_check":       self._skill_email_check,
            # Calendar
            "calendar_today":    self._skill_calendar_today,
            "calendar_add":      self._skill_calendar_add,
            "calendar_week":     self._skill_calendar_week,
            # Browser
            "browser_open":      self._skill_browser_open,
            "browser_click":     self._skill_browser_click,
            "browser_type":      self._skill_browser_type,
            "browser_scrape":    self._skill_browser_scrape,
            # Smart Home
            "fan":               self._skill_fan,
            "smart_light":       self._skill_smart_light,
            "smart_ac":          self._skill_smart_ac,
            # Plugin
            "plugin_list":       self._skill_plugin_list,
            "plugin_reload":     self._skill_plugin_reload,
            # Knowledge Base
            "kb_search":         self._skill_kb_search,
            "kb_rebuild":        self._skill_kb_rebuild,
            "kb_list":           self._skill_kb_list,
            "kb_stats":          self._skill_kb_stats,
        }
        try:
            pl = self.plugin_loader
            for name in pl.handlers:
                base[name] = lambda *args, n=name: pl.execute(n, *args)
        except Exception:
            pass
        return base

    # ════════════════════════════════════════════
    # DISPATCHER
    # ════════════════════════════════════════════

    async def parse_and_execute(self, response_text: str, memory_context: str = "") -> Dict[str, Any]:
        match = self.SKILL_PATTERN.search(response_text)
        if not match:
            return {"executed": False, "clean_text": response_text, "is_data_skill": False}

        skill_name = match.group(1).lower()
        params_str = match.group(2) or ""
        if skill_name in ("web_open", "browser_open"):
            params = [params_str.strip()] if params_str.strip() else []
        else:
            params = [p.strip() for p in params_str.split(":") if p.strip()]
        clean_text = re.sub(r' {2,}', ' ', self.SKILL_PATTERN.sub("", response_text)).strip()

        if skill_name not in self.skills_registry:
            logger.warning(f"Unknown skill: {skill_name}")
            return {"executed": False, "clean_text": clean_text, "is_data_skill": False}

        try:
            logger.info(f"⚙️  {skill_name}({params})")
            raw    = self.skills_registry[skill_name](*params)
            result = await raw if asyncio.iscoroutine(raw) else raw
            result_str = str(result) if result else ""
            return {
                "executed":      True,
                "skill_name":    skill_name,
                "params":        params,
                "result":        result_str,
                "tts_result":    _truncate_for_tts(result_str, skill_name),
                "clean_text":    clean_text,
                "is_data_skill": skill_name in DATA_SKILLS,
            }
        except Exception as e:
            import traceback
            logger.error(f"Skill '{skill_name}' failed: {e}\n{traceback.format_exc()}")
            return {"executed": False, "error": str(e), "clean_text": clean_text, "is_data_skill": False}

    # ════════════════════════════════════════════
    # SYSTEM INFO SKILLS  ← NEW
    # ════════════════════════════════════════════

    def _skill_time_now(self) -> str:
        now = datetime.now()
        return now.strftime("Time: %H:%M")

    def _skill_date_today(self) -> str:
        today = datetime.now()
        return today.strftime("Date: %Y-%m-%d")

    def _skill_sysinfo(self, detail: str = "all") -> str:
        from modules.sysinfo import get_system_info
        return get_system_info(detail)

    def _skill_top_processes(self, n: str = "5") -> str:
        from modules.sysinfo import get_top_processes
        return get_top_processes(int(n) if n.isdigit() else 5)

    # ════════════════════════════════════════════
    # MEDIA CONTROL SKILL  ← NEW
    # ════════════════════════════════════════════

    def _skill_media(self, action: str = "play", *args) -> str:
        from modules.media_control import media_action
        return media_action(action)

    # ════════════════════════════════════════════
    # REMINDER SKILLS  ← NEW
    # ════════════════════════════════════════════

    def _skill_reminder_set(self, *args) -> str:
        from modules.reminder_agent import set_reminder
        # args: text, date (YYYY-MM-DD), time (HH:MM optional)
        if len(args) < 2:
            return "Usage: reminder_set:text:YYYY-MM-DD:HH:MM"
        text     = args[0]
        date_str = args[1]
        time_str = args[2] if len(args) > 2 else "09:00"
        return set_reminder(self.config, text, date_str, time_str)

    def _skill_reminder_list(self, *args) -> str:
        from modules.reminder_agent import list_reminders
        return list_reminders(self.config)

    def _skill_reminder_clear(self, *args) -> str:
        from modules.reminder_agent import clear_reminders
        return clear_reminders(self.config)

    # ════════════════════════════════════════════
    # CODE / FILE WRAPPERS
    # ════════════════════════════════════════════

    def _skill_write_code(self, *a):       return self.code_engine.write_code(*a)
    def _skill_run_code(self, *a):         return self.code_engine.run_code(*a)
    def _skill_code_review(self, *a):      return self.code_engine.code_review(*a)
    def _skill_fix_code(self, *a):         return self.code_engine.fix_code(*a)
    def _skill_project_scaffold(self, *a): return self.code_engine.project_scaffold(*a)
    def _skill_find_and_explain(self, *a): return self.file_manager.find_and_explain(*a)
    def _skill_list_files(self, *a):       return self.file_manager.list_files(*a)
    def _skill_read_file(self, *a):        return self.file_manager.read_file(*a)
    def _skill_edit_file(self, *a):        return self.file_manager.edit_file(*a)
    def _skill_search_files(self, *a):     return self.file_manager.search_files(*a)

    # ════════════════════════════════════════════
    # INFORMATION SKILLS
    # ════════════════════════════════════════════

    def _skill_weather(self, city: str = "auto") -> str:
        try:
            import httpx
            url = f"https://wttr.in/{city.strip() or 'auto'}?format=3&lang=en"
            with httpx.Client(timeout=7.0) as c:
                r = c.get(url, headers={"User-Agent": "curl/7.68.0"})
                return r.text.strip() if r.status_code == 200 else f"Weather unavailable for {city}."
        except Exception:
            return "Could not reach weather server."

    def _skill_web_search(self, *args) -> str:
        import httpx
        query = " ".join(args).strip()
        if not query:
            return "What should I search for?"
        try:
            encoded = query.replace(" ", "+")
            rss = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
            with httpx.Client(timeout=7.0) as c:
                resp = c.get(rss, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    root  = ET.fromstring(resp.content)
                    items = root.findall('.//item')[:4]
                    headlines = []
                    for item in items:
                        t = item.find('title')
                        if t is not None and t.text:
                            title = t.text.strip()
                            if " - " in title:
                                title = title.rsplit(" - ", 1)[0]
                            headlines.append(title)
                    if headlines:
                        return ". ".join(headlines[:3])
        except Exception as e:
            logger.warning(f"News RSS failed: {e}")
        try:
            params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
            with httpx.Client(timeout=5.0) as c:
                data = c.get("https://api.duckduckgo.com/", params=params).json()
                abstract = data.get("AbstractText", "").strip()
                if abstract:
                    return abstract[:300]
        except Exception:
            pass
        webbrowser.open(f"https://duckduckgo.com/?q={query.replace(' ', '+')}")
        return f"Opened browser search for '{query}'."

    def _skill_youtube_search(self, *args) -> str:
        query = " ".join(args).strip()
        webbrowser.open(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}")
        return "YouTube search opened."

    def _skill_clear_memory(self) -> str:
        return "Memory cleared."

    def _skill_add_rule(self, *args) -> str:
        import json
        text = " ".join(args).strip()
        if not text:
            return "Rule text is missing."
        path = Path(self.config.DATA_DIR) / "permanent_rules.json"
        rules = json.loads(path.read_text()) if path.exists() else []
        rules.append({"rule": text, "added_at": datetime.now().isoformat()})
        path.write_text(json.dumps(rules, indent=2))
        return "Rule saved."

    def _skill_timer(self, seconds: str = "60", label: str = "Timer") -> str:
        try:
            secs = int(seconds)
            if secs <= 0:
                return "Timer needs a positive duration."

            def _countdown():
                time.sleep(secs)
                msg = f"MAX: {label} done! ({secs}s)"
                try:
                    from plyer import notification
                    notification.notify(title="MAX Timer", message=msg, timeout=8)
                    return
                except ImportError:
                    pass
                if PYAUTOGUI_AVAILABLE:
                    try:
                        pyautogui.alert(text=msg, title="MAX Timer", button="OK")
                        return
                    except Exception:
                        pass
                if platform.system() == "Windows":
                    subprocess.run([
                        "powershell", "-Command",
                        f"Add-Type -AssemblyName System.Windows.Forms; "
                        f"[System.Windows.Forms.MessageBox]::Show('{msg}','MAX')"
                    ], capture_output=True)

            threading.Thread(target=_countdown, daemon=True).start()
            mins, rem = divmod(secs, 60)
            return f"Timer set: {f'{mins}m {rem}s' if mins else f'{secs}s'}."
        except ValueError:
            return "Provide duration in seconds."

    def _skill_note(self, *args) -> str:
        try:
            text = " ".join(args).strip()
            if not text:
                return "Note content is empty."
            notes_file = Path(self.config.DATA_DIR) / "notes.txt"
            notes_file.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(notes_file, 'a', encoding='utf-8') as f:
                f.write(f"[{ts}] {text}\n")
            return "Note saved."
        except Exception as e:
            return f"Note save failed: {e}"

    # ════════════════════════════════════════════
    # SCREEN / VISION
    # ════════════════════════════════════════════

    async def _skill_read_screen(self, *args) -> str:
        target = " ".join(args).strip()
        try:
            import pyautogui as pg
            ss_dir = Path(self.config.DATA_DIR) / "screenshots"
            ss_dir.mkdir(parents=True, exist_ok=True)
            path = ss_dir / "vision_debug.jpg"
            region = None
            if target and target.lower() != "all":
                try:
                    import pygetwindow as gw
                    wins = gw.getWindowsWithTitle(target)
                    if wins:
                        w = wins[0]
                        try: w.activate(); time.sleep(0.7)
                        except Exception: pass
                        region = (w.left, w.top, w.width, w.height)
                except ImportError:
                    pass
            pg.screenshot(region=region).convert('RGB').save(str(path), quality=85)
            from modules.llm import analyze_image_with_prompt
            return await analyze_image_with_prompt(str(path),
                f"Describe what's visible on the '{target or 'screen'}'. Read URLs and text.")
        except ImportError:
            return "pyautogui needed: pip install pyautogui"
        except Exception as e:
            return f"Screen read failed: {e}"

    def _skill_list_windows(self, *args) -> str:
        try:
            import pygetwindow as gw
            titles = [t for t in gw.getAllTitles() if t.strip()]
            return "Open windows: " + ", ".join(titles[:10]) if titles else "No active windows."
        except ImportError:
            return "pygetwindow needed: pip install pygetwindow"

    def _skill_screenshot(self, filename: str = "", **kw) -> str:
        if not PYAUTOGUI_AVAILABLE:
            return "pyautogui needed: pip install pyautogui"
        try:
            sd = Path(self.config.DATA_DIR) / "screenshots"
            sd.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fp = sd / f"{filename.strip() or 'max_screenshot'}_{ts}.png"
            pyautogui.screenshot(str(fp))
            return f"Screenshot saved: {fp.name}"
        except Exception as e:
            return f"Screenshot failed: {e}"

    # ════════════════════════════════════════════
    # PC CONTROL — open_app (4-step chain)
    # ════════════════════════════════════════════

    _WIN_PROTOCOLS: Dict[str, str] = {
        "whatsapp": "whatsapp:", "spotify": "spotify:", "discord": "discord:",
        "teams": "msteams:", "ms-teams": "msteams:", "microsoft teams": "msteams:",
        "slack": "slack:", "zoom": "zoommtg://", "telegram": "tg:", "skype": "skype:",
    }
    _WIN_DIRECT: Dict[str, str] = {
        "notepad": "notepad.exe", "calculator": "calc.exe", "calc": "calc.exe",
        "paint": "mspaint.exe", "cmd": "cmd.exe", "command prompt": "cmd.exe",
        "terminal": "wt.exe", "windows terminal": "wt.exe", "powershell": "powershell.exe",
        "explorer": "explorer.exe", "file explorer": "explorer.exe",
        "task manager": "taskmgr.exe", "taskmgr": "taskmgr.exe",
        "chrome": "chrome", "google chrome": "chrome", "firefox": "firefox",
        "edge": "msedge", "brave": "brave", "opera": "opera",
        "vscode": "code", "vs code": "code", "visual studio code": "code",
        "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
        "outlook": "outlook", "vlc": "vlc", "obs": "obs64",
        "pycharm": "pycharm64", "postman": "postman", "figma": "figma",
    }

    def _skill_open_app(self, app_name: str = "", **kw) -> str:
        if not app_name:
            return "Which app should I open?"
        system    = platform.system()
        app_lower = app_name.lower().strip()
        web_map   = getattr(self.config, 'WEB_FALLBACK_MAP', {})

        if system == "Windows":
            # Step 1: Protocol handler
            proto = self._WIN_PROTOCOLS.get(app_lower)
            if proto:
                try:
                    os.startfile(proto)
                    return f"{app_name} opened."
                except Exception as e:
                    logger.warning(f"Protocol failed for '{app_name}': {e}")

            # Step 2: Direct exe
            exe = self._WIN_DIRECT.get(app_lower)
            if exe:
                try:
                    subprocess.Popen(exe, shell=True)
                    return f"{app_name} opened."
                except Exception as e:
                    logger.warning(f"Direct exe failed for '{app_name}': {e}")

            # Step 3: App indexer (fuzzy, all installed apps)
            try:
                match = self.app_indexer.find_app(app_lower)
                if match:
                    matched_name, app_path = match
                    os.startfile(app_path)
                    return f"{matched_name.title() or app_name} opened."
            except Exception as e:
                logger.warning(f"App indexer failed for '{app_name}': {e}")

            # Step 4: Shell fallback
            try:
                subprocess.Popen(app_lower, shell=True)
                return f"{app_name} opened."
            except Exception:
                pass

        elif system == "Darwin":
            mac_map = getattr(self.config, 'MAC_APP_MAP', {})
            try:
                subprocess.run(["open", "-a", mac_map.get(app_lower, app_name)], check=True)
                return f"{app_name} opened."
            except Exception as e:
                logger.warning(f"macOS open failed: {e}")

        else:
            try:
                subprocess.Popen([app_lower])
                return f"{app_name} opened."
            except Exception:
                pass

        fallback = web_map.get(app_lower)
        if fallback:
            webbrowser.open(fallback)
            return f"{app_name} not found locally. Opened in browser."
        return f"Could not find '{app_name}'. Try: 'rebuild app index' first."

    def _skill_list_apps(self, *args) -> str:
        query = " ".join(args).strip()
        try:
            apps = self.app_indexer.list_apps(query, limit=30)
            if not apps:
                return f"No apps found for '{query}'. Try rebuilding the index."
            label = f"Apps matching '{query}':" if query else f"Installed apps ({len(apps)} shown):"
            return label + "\n" + "\n".join(f"  • {a}" for a in apps)
        except Exception as e:
            return f"App list failed: {e}"

    def _skill_rebuild_app_index(self, *args) -> str:
        try:
            count = self.app_indexer.build_index()
            return f"App index rebuilt. {count} apps indexed."
        except Exception as e:
            return f"Rebuild failed: {e}"

    def _skill_web_open(self, url: str = "", **kw) -> str:
        if not url:
            return "Provide a URL."
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            webbrowser.open(url)
            return "URL opened in browser."
        except Exception as e:
            return f"Could not open URL: {e}"

    def _skill_volume_control(self, action: str = "up", value: str = "10", **kw) -> str:
        try:
            system = platform.system()
            al = action.lower()
            if system == "Windows":
                try:
                    import comtypes
                    comtypes.CoInitialize()
                    from ctypes import cast, POINTER
                    from comtypes import CLSCTX_ALL
                    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                    devices  = AudioUtilities.GetSpeakers()
                    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    vol = cast(interface, POINTER(IAudioEndpointVolume))
                    step = int(value) / 100.0
                    if al == "up":    vol.SetMasterVolumeLevelScalar(min(1.0, vol.GetMasterVolumeLevelScalar() + step), None)
                    elif al == "down": vol.SetMasterVolumeLevelScalar(max(0.0, vol.GetMasterVolumeLevelScalar() - step), None)
                    elif al == "mute": vol.SetMute(not vol.GetMute(), None)
                    elif al == "set":  vol.SetMasterVolumeLevelScalar(min(1.0, int(value) / 100.0), None)
                    comtypes.CoUninitialize()   
                    return f"Volume {al}."
                except ImportError as e:
                    return f"Volume control missing dependency: {e}. Try: pip install pycaw comtypes"
            elif system == "Darwin":
                if al == "mute": subprocess.run(["osascript", "-e", "set volume output muted true"])
                else: subprocess.run(["osascript", "-e", f"set volume output volume {max(0,min(100,int(value)))}"])
                return "Volume adjusted."
            else:
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{value}%"])
                return f"Volume set to {value}%."
        except Exception as e:
            return f"Volume control failed: {e}"

    def _skill_brightness(self, action: str = "up", value: str = "10") -> str:
        try:
            if platform.system() == "Windows":
                import wmi
                w = wmi.WMI(namespace='wmi')
                methods = w.WmiMonitorBrightnessMethods()[0]
                current = w.WmiMonitorBrightness()[0].CurrentBrightness
                step = int(value)
                new_val = (min(100, current + step) if action.lower() == "up"
                           else max(0, current - step) if action.lower() == "down"
                           else max(0, min(100, int(value))))
                methods.WmiSetBrightness(new_val, 0)
                return f"Brightness set to {new_val}%."
            elif platform.system() == "Darwin":
                subprocess.run(["osascript", "-e", "tell application \"System Events\" to key code 144"])
                return "Brightness adjusted."
            else:
                subprocess.run(["brightnessctl", "set", f"{value}%"])
                return f"Brightness {value}%."
        except ImportError:
            return "Brightness needs: pip install wmi pywin32"
        except Exception as e:
            return f"Brightness failed: {str(e)[:120]}"

    def _skill_clipboard(self, action: str = "get", text: str = "") -> str:
        try:
            import pyperclip
            if action.lower() == "get":
                content = pyperclip.paste()
                return f"Clipboard: {content[:200]}" if content else "Clipboard is empty."
            elif action.lower() == "set":
                if not text: return "What should I copy to clipboard?"
                pyperclip.copy(text)
                return "Copied to clipboard."
            return "Use 'get' or 'set'."
        except ImportError:
            return "Clipboard needs: pip install pyperclip"
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
            return "PC locked."
        except Exception as e:
            return f"Lock failed: {str(e)[:120]}"
    
    def _skill_youtube_play(self, *args) -> str:
        """Directly plays the first video matching the query on YouTube."""
        if not PYWHATKIT_AVAILABLE:
            return "YouTube play needs: pip install pywhatkit"
        query = " ".join(args).strip()
        if not query:
            return "What should I play on YouTube?"
        try:
            # Ye direct video open karke play kar dega
            pywhatkit.playonyt(query)
            return f"Playing '{query}' on YouTube."
        except Exception as e:
            return f"YouTube play failed: {e}"
    
    def _skill_whatsapp_message(self, contact: str = "", message: str = "", **kw) -> str:
        if not PYWHATKIT_AVAILABLE: return "WhatsApp needs: pip install pywhatkit"
        if not contact: return "Provide contact number (+91 format)."
        if not message: return "What message should I send?"
        if not contact.startswith("+"): contact = "+" + contact
        try:
            pywhatkit.sendwhatmsg_instantly(phone_no=contact, message=message, wait_time=15, tab_close=True, close_time=3)
            return "WhatsApp message sent."
        except Exception as e:
            return f"WhatsApp failed: {e}"

    def _skill_type_text(self, *args) -> str:
        if not PYAUTOGUI_AVAILABLE: return "Typing needs: pip install pyautogui"
        text = " ".join(args).strip()
        if not text: return "What should I type?"
        try:
            time.sleep(1.5)
            pyautogui.write(text, interval=0.04)
            return "Typed."
        except Exception as e:
            return f"Typing failed: {e}"

    def _skill_system_shutdown(self, delay: str = "30", **kw) -> str:
        try:
            secs = max(0, int(delay))
            if platform.system() == "Windows": subprocess.run(["shutdown", "/s", "/t", str(secs)], check=True)
            else: subprocess.run(["sudo", "shutdown", "-h", f"+{max(1,secs//60)}"], check=True)
            return f"Shutting down in {secs}s. Save your work."
        except Exception as e: return f"Shutdown failed: {e}"

    def _skill_system_restart(self, delay: str = "30", **kw) -> str:
        try:
            secs = max(0, int(delay))
            if platform.system() == "Windows": subprocess.run(["shutdown", "/r", "/t", str(secs)], check=True)
            else: subprocess.run(["sudo", "shutdown", "-r", f"+{max(1,secs//60)}"], check=True)
            return f"Restarting in {secs}s."
        except Exception as e: return f"Restart failed: {e}"

    # ════════════════════════════════════════════
    # EMAIL / CALENDAR / BROWSER / SMART HOME
    # ════════════════════════════════════════════

    def _skill_email_send(self, to="", subject="", body=""): return self.email_agent.send_email(to, subject, body)
    def _skill_email_check(self, *a): return self.email_agent.check_emails()
    def _skill_calendar_today(self, *a): return self.calendar_agent.today()
    def _skill_calendar_week(self, *a): return self.calendar_agent.week()
    def _skill_calendar_add(self, *a):
        if len(a) < 2: return "Usage: calendar_add:title:YYYY-MM-DD:HH:MM"
        return self.calendar_agent.add_event(a[0], a[1], a[2] if len(a) > 2 else "")
    def _skill_browser_open(self, *a): return self.browser_agent.open_url(a[0] if a else "")
    def _skill_browser_click(self, *a): return self.browser_agent.click(a[0] if a else "")
    def _skill_browser_type(self, *a):
        if len(a) < 2: return "Usage: browser_type:selector:text"
        return self.browser_agent.type_text(a[0], a[1])
    def _skill_browser_scrape(self, *a):
        if len(a) < 2: return "Usage: browser_scrape:url:query"
        return self.browser_agent.scrape(a[0], a[1])
    def _skill_fan(self, *a): return self.smarthome_agent.fan_control(a[0] if a else "on", a[1] if len(a)>1 else "")
    def _skill_smart_light(self, *a): return self.smarthome_agent.light_control(a[0] if a else "on", a[1] if len(a)>1 else "")
    def _skill_smart_ac(self, *a): return self.smarthome_agent.ac_control(a[0] if a else "on", a[1] if len(a)>1 else "")
    def _skill_plugin_list(self, *a): return self.plugin_loader.list_plugins()
    def _skill_plugin_reload(self, *a):
        self.plugin_loader.reload()
        self.skills_registry = self._register_skills()
        return "Plugins reloaded."

    # ════════════════════════════════════════════
    # KNOWLEDGE BASE SKILLS  ← NEW
    # ════════════════════════════════════════════

    def _skill_kb_search(self, *args) -> str:
        """Manual KB search — bypasses auto-injection to show raw results."""
        query = " ".join(args).strip()
        if not query:
            return "What should I search in the knowledge base?"
        try:
            from modules.knowledge_base import get_knowledge_base
            kb  = get_knowledge_base(self.config)
            ctx = kb.query(query, top_k=3, min_similarity=0.20)
            if ctx:
                return ctx
            return f"Nothing relevant found in knowledge base for: '{query}'."
        except Exception as e:
            return f"KB search failed: {e}"

    def _skill_kb_rebuild(self, *args) -> str:
        """Rebuild the full knowledge base index from .md files."""
        try:
            from modules.knowledge_base import get_knowledge_base
            result = get_knowledge_base(self.config).build_index()
            if "error" in result:
                return result["error"]
            files  = result.get("files", 0)
            chunks = result.get("chunks", 0)
            indexed = result.get("indexed", [])
            msg = f"Knowledge base rebuilt: {files} file(s), {chunks} chunks indexed."
            if indexed:
                msg += "\n" + "\n".join(f"  • {f}" for f in indexed)
            return msg
        except Exception as e:
            return f"KB rebuild failed: {e}"

    def _skill_kb_list(self, *args) -> str:
        """List all .md files in the knowledge folder."""
        try:
            from modules.knowledge_base import get_knowledge_base
            return get_knowledge_base(self.config).list_documents()
        except Exception as e:
            return f"KB list failed: {e}"

    def _skill_kb_stats(self, *args) -> str:
        """Show knowledge base stats (chunks, files, paths)."""
        try:
            from modules.knowledge_base import get_knowledge_base
            stats = get_knowledge_base(self.config).get_stats()
            if not stats.get("ready"):
                return f"Knowledge base not ready. {stats.get('error', '')}"
            return (
                f"Knowledge base stats:\n"
                f"  • Indexed chunks : {stats['chunks']}\n"
                f"  • .md files      : {stats['md_files']}\n"
                f"  • KB folder      : {stats['kb_dir']}\n"
                f"  • ChromaDB path  : {stats['chroma_dir']}"
            )
        except Exception as e:
            return f"KB stats failed: {e}"


# ══════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════

_skills_instance: Optional[SkillsEngine] = None


def get_skills_engine(config) -> SkillsEngine:
    global _skills_instance
    if _skills_instance is None:
        _skills_instance = SkillsEngine(config)
    return _skills_instance
