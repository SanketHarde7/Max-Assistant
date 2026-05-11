"""
media_control.py — MAX v4.2
Controls media playback via OS-level media keys.
Windows: uses keyboard library or ctypes VK codes.
macOS: uses osascript.
Linux: uses playerctl or keyboard library.

Install: pip install keyboard   (Windows/Linux)
"""
import logging
import platform
import subprocess
from typing import Optional

logger = logging.getLogger("MAX.MEDIA")

# Mapping of action names to Windows Virtual Key codes
_VK_MEDIA = {
    "play":     0xB3,   # VK_MEDIA_PLAY_PAUSE
    "pause":    0xB3,   # same key
    "stop":     0xB2,   # VK_MEDIA_STOP
    "next":     0xB0,   # VK_MEDIA_NEXT_TRACK
    "previous": 0xB1,   # VK_MEDIA_PREV_TRACK
    "prev":     0xB1,
    "back":     0xB1,
}

_ALIASES = {
    "playpause": "play",
    "pp":        "play",
    "fwd":       "next",
    "forward":   "next",
    "rewind":    "previous",
    "rw":        "previous",
    "bk":        "previous",
}


def media_action(action: str) -> str:
    """
    Send a media key press to the OS.
    action: play | pause | stop | next | previous | prev
    """
    action_clean = _ALIASES.get(action.lower().strip(), action.lower().strip())

    system = platform.system()

    if system == "Windows":
        return _windows_media(action_clean)
    elif system == "Darwin":
        return _macos_media(action_clean)
    else:
        return _linux_media(action_clean)


def _windows_media(action: str) -> str:
    vk = _VK_MEDIA.get(action)
    if vk is None:
        return f"Unknown media action '{action}'. Use: play, pause, stop, next, previous."

    # Method 1: ctypes (no external libs needed)
    try:
        import ctypes
        KEYEVENTF_EXTENDEDKEY = 0x0001
        KEYEVENTF_KEYUP       = 0x0002
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
        label = "Play/Pause" if action in ("play", "pause") else action.capitalize()
        logger.info(f"Media key sent: {label}")
        return f"Media: {label}."
    except Exception as e:
        logger.warning(f"ctypes media key failed: {e}")

    # Method 2: keyboard library fallback
    try:
        import keyboard
        key_map = {
            "play":     "play/pause media",
            "pause":    "play/pause media",
            "stop":     "stop media",
            "next":     "next track",
            "previous": "previous track",
            "prev":     "previous track",
        }
        key = key_map.get(action)
        if key:
            keyboard.send(key)
            return f"Media: {action.capitalize()}."
    except ImportError:
        return "Media control needs: pip install keyboard"
    except Exception as e:
        return f"Media control failed: {e}"

    return f"Media action '{action}' failed on Windows."


def _macos_media(action: str) -> str:
    # macOS: use osascript to control Music/Spotify
    scripts = {
        "play":     'tell application "Music" to play',
        "pause":    'tell application "Music" to pause',
        "stop":     'tell application "Music" to stop',
        "next":     'tell application "Music" to next track',
        "previous": 'tell application "Music" to previous track',
        "prev":     'tell application "Music" to previous track',
    }
    script = scripts.get(action)
    if not script:
        return f"Unknown media action '{action}'."
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        return f"Media: {action.capitalize()}."
    except Exception as e:
        return f"macOS media control failed: {e}"


def _linux_media(action: str) -> str:
    # Linux: try playerctl first, then keyboard
    playerctl_map = {
        "play":     ["playerctl", "play"],
        "pause":    ["playerctl", "pause"],
        "stop":     ["playerctl", "stop"],
        "next":     ["playerctl", "next"],
        "previous": ["playerctl", "previous"],
        "prev":     ["playerctl", "previous"],
    }
    cmd = playerctl_map.get(action)
    if cmd:
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return f"Media: {action.capitalize()}."
        except FileNotFoundError:
            pass
        except Exception as e:
            return f"playerctl failed: {e}"

    try:
        import keyboard
        key_map = {
            "play":  "play/pause media", "pause": "play/pause media",
            "next":  "next track",       "previous": "previous track",
            "prev":  "previous track",   "stop": "stop media",
        }
        key = key_map.get(action)
        if key:
            keyboard.send(key)
            return f"Media: {action.capitalize()}."
    except ImportError:
        return "Media control on Linux needs: pip install keyboard"
    except Exception as e:
        return f"Media control failed: {e}"

    return f"Could not control media on Linux. Install playerctl: sudo apt install playerctl"
