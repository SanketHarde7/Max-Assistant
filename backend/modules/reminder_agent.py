"""
reminder_agent.py — MAX v4.2
Persistent reminder system.
- Reminders stored in data/reminders.json
- Background daemon thread checks every 30 seconds
- Fires desktop notification (plyer) when time comes
- Skills: reminder_set, reminder_list, reminder_clear
"""
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger("MAX.REMINDER")


# ═══════════════════════════════════════
# Storage helpers
# ═══════════════════════════════════════

def _reminder_file(config) -> Path:
    return Path(config.DATA_DIR) / "reminders.json"


def _load(config) -> List[Dict]:
    f = _reminder_file(config)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(config, reminders: List[Dict]):
    _reminder_file(config).write_text(
        json.dumps(reminders, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _notify(title: str, message: str):
    """Fire desktop notification. Falls back to print if plyer unavailable."""
    try:
        from plyer import notification
        notification.notify(title=title, message=message, app_name="MAX", timeout=10)
        return
    except ImportError:
        pass
    # Windows PowerShell fallback
    try:
        import subprocess, platform
        if platform.system() == "Windows":
            subprocess.run([
                "powershell", "-Command",
                f'Add-Type -AssemblyName System.Windows.Forms; '
                f'[System.Windows.Forms.MessageBox]::Show("{message}","MAX Reminder")'
            ], capture_output=True)
            return
    except Exception:
        pass
    logger.info(f"[REMINDER] {title}: {message}")


# ═══════════════════════════════════════
# Background daemon
# ═══════════════════════════════════════

class ReminderDaemon(threading.Thread):
    """Checks reminders every 30 seconds. Runs as daemon thread."""

    def __init__(self, config):
        super().__init__(daemon=True, name="MAX-ReminderDaemon")
        self.config = config
        self._stop_event = threading.Event()

    def run(self):
        logger.info("Reminder daemon started.")
        while not self._stop_event.is_set():
            try:
                self._check()
            except Exception as e:
                logger.error(f"Reminder check error: {e}")
            self._stop_event.wait(timeout=30)

    def stop(self):
        self._stop_event.set()

    def _check(self):
        now = datetime.now()
        reminders = _load(self.config)
        pending   = []
        fired     = False

        for r in reminders:
            due_str = r.get("due")
            if not due_str:
                continue
            try:
                due = datetime.fromisoformat(due_str)
            except Exception:
                pending.append(r)  # keep malformed entries
                continue

            if due <= now and not r.get("fired"):
                _notify("MAX Reminder", r.get("text", "Reminder!"))
                r["fired"] = True
                fired = True
                logger.info(f"Reminder fired: {r['text']}")

            # Keep unfired, and keep fired ones for 24h for history
            pending.append(r)

        if fired:
            _save(self.config, pending)


# ═══════════════════════════════════════
# Public skill functions
# ═══════════════════════════════════════

def set_reminder(config, text: str, date_str: str, time_str: str = "09:00") -> str:
    """
    Add a reminder.
    date_str: YYYY-MM-DD
    time_str: HH:MM (default 09:00)
    """
    if not text:
        return "What should I remind you about?"
    if not date_str:
        return "Reminder needs a date. Format: YYYY-MM-DD"

    # Validate datetime
    dt_str = f"{date_str} {time_str or '09:00'}"
    try:
        due = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    except ValueError:
        return f"Invalid date/time format. Use YYYY-MM-DD and HH:MM."

    if due < datetime.now():
        return f"That time has already passed ({dt_str}). Set a future time."

    reminder = {
        "id":      f"r_{int(time.time())}",
        "text":    text,
        "due":     due.isoformat(),
        "created": datetime.now().isoformat(),
        "fired":   False,
    }
    reminders = _load(config)
    reminders.append(reminder)
    _save(config, reminders)

    friendly = due.strftime("%b %d at %I:%M %p")
    logger.info(f"Reminder set: '{text}' at {friendly}")
    return f"Reminder set: '{text}' — {friendly}."


def list_reminders(config) -> str:
    """List all pending (unfired) reminders."""
    reminders = _load(config)
    pending = [r for r in reminders if not r.get("fired")]
    if not pending:
        return "No reminders set."
    pending.sort(key=lambda x: x.get("due", ""))
    lines = [f"{len(pending)} reminder(s) scheduled:"]
    for r in pending:
        try:
            due = datetime.fromisoformat(r["due"]).strftime("%b %d, %I:%M %p")
        except Exception:
            due = r.get("due", "?")
        lines.append(f"  • {r['text']} — {due}")
    return "\n".join(lines)


def clear_reminders(config) -> str:
    """Remove all reminders."""
    _save(config, [])
    return "All reminders cleared."


# ═══════════════════════════════════════
# Singleton daemon
# ═══════════════════════════════════════

_daemon: Optional[ReminderDaemon] = None


def start_reminder_daemon(config):
    """Call once at startup to begin background checking."""
    global _daemon
    if _daemon is None or not _daemon.is_alive():
        _daemon = ReminderDaemon(config)
        _daemon.start()
        logger.info("Reminder daemon launched.")
