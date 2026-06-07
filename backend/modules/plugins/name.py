# Path: backend/modules/plugins/name.py
# Use: Component file for the Jarvis desktop assistant application.
"""
name.py — MAX plugin
description
"""

def handle_name(*args):
    text = " ".join(args).strip()
    if not text:
        return "Provide input for this skill."
    return f"Received: {text}"


def register():
    return {
        "skill_name": "name",
        "description": "description",
        "handler": handle_name,
    }
