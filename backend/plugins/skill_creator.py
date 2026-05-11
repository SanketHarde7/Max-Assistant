"""
skill_creator.py — MAX plugin
Creates a new skill plugin skeleton in backend/plugins.
"""
import re
from pathlib import Path
from typing import List
from config import config


def _sanitize_name(raw: str) -> str:
    name = raw.strip().lower()
    name = re.sub(r"[\s\-]+", "_", name)
    name = re.sub(r"[^a-z0-9_]", "", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name


def _safe_identifier(name: str) -> str:
    if not name:
        return "skill"
    if re.match(r"^[a-zA-Z_]", name):
        return name
    return f"skill_{name}"


def _build_plugin_source(skill_name: str, description: str) -> str:
    ident = _safe_identifier(skill_name)
    handler_name = f"handle_{ident}"
    desc = description or f"Custom skill '{skill_name}'."
    return (
        '"""\n'
        f"{skill_name}.py — MAX plugin\n"
        f"{desc}\n"
        '"""\n'
        "\n"
        "def " + handler_name + "(*args):\n"
        "    text = \" \".join(args).strip()\n"
        "    if not text:\n"
        "        return \"Provide input for this skill.\"\n"
        "    return f\"Received: {text}\"\n\n"
        "\n"
        "def register():\n"
        "    return {\n"
        f"        \"skill_name\": \"{skill_name}\",\n"
        f"        \"description\": \"{desc}\",\n"
        f"        \"handler\": {handler_name},\n"
        "    }\n"
    )


def handle_skill_creator(*args: List[str]) -> str:
    if not args:
        return "Usage: skill_creator:skill_name:description (description optional)."

    raw_name = args[0]
    desc = ":".join(args[1:]).strip()

    safe_name = _sanitize_name(raw_name)
    if not safe_name:
        return "Invalid skill name. Use letters, numbers, spaces, or dashes."

    target_path = Path(config.PLUGINS_DIR) / f"{safe_name}.py"
    if target_path.exists():
        return f"Skill already exists: {target_path.name}. Choose a different name or delete it first."

    source = _build_plugin_source(safe_name, desc)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(source, encoding="utf-8")

    return (
        f"Skill template created: {target_path.name}. "
        "Restart the backend or run 'plugin_reload' to load it."
    )


def register():
    return {
        "skill_name": "skill_creator",
        "description": "Create a new MAX skill plugin skeleton in backend/plugins.",
        "handler": handle_skill_creator,
    }
