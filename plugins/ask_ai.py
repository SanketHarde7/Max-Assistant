import httpx
import psutil
import pyperclip
import pyautogui
import webbrowser

SKILL_NAME = "ask_ai"
DESCRIPTION = "Ask AI about a topic"

def execute(*args) -> str:
    try:
        if len(args) < 2:
            return "Error: Not enough arguments"
        topic = ' '.join(args[1:])
        url = f"https://www.google.com/search?q={topic}"
        webbrowser.open(url)
        return f"Searching for '{topic}' on Google"
    except Exception as e:
        return f"Error: {str(e)}"