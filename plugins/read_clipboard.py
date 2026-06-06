import httpx
import pyperclip
import pyautogui

SKILL_NAME = "read_clipboard"
DESCRIPTION = "Reads the clipboard content."

def execute(*args) -> str:
    try:
        clipboard_content = pyperclip.paste()
        return f"Clipboard content: {clipboard_content}"
    except Exception as e:
        return f"Failed to read clipboard: {str(e)}"