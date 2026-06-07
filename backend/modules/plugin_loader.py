# Path: backend/modules/plugin_loader.py
# Use: Dynamically loads and registers third-party plugins.
"""
plugin_loader.py — MAX v4.0
Dynamic plugin system. Zero config auto-loading.
- Each plugin = one Python file in plugins/ folder
- Must have register() function returning skill metadata
- On startup, auto-load and register all plugins
"""
import os
import sys
import importlib
import logging
from pathlib import Path
from typing import Dict, List, Any, Callable, Optional
from config import config

logger = logging.getLogger("MAX.PLUGINS")


class PluginLoader:
    """Dynamic plugin loader for extensible skills."""

    def __init__(self):
        self.plugins_dir = config.PLUGINS_DIR
        self.loaded_plugins: Dict[str, Any] = {}
        self.handlers: Dict[str, Callable] = {}

    def discover(self) -> List[Path]:
        """Find all .py files in plugins/ (skip __init__)."""
        if not self.plugins_dir.exists():
            return []
        files = []
        for f in self.plugins_dir.iterdir():
            if f.is_file() and f.suffix == ".py" and not f.name.startswith("_"):
                files.append(f)
        return files

    def load(self, filepath: Path) -> Dict[str, Any]:
        """Load a single plugin file."""
        module_name = f"jarvis_plugin_{filepath.stem}"
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if not spec or not spec.loader:
            return {}
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        if not hasattr(module, "register"):
            logger.warning(f"Plugin {filepath.name} has no register() — skipped.")
            return {}

        reg = module.register()
        if not isinstance(reg, dict):
            logger.warning(f"Plugin {filepath.name} register() didn't return dict — skipped.")
            return {}

        name = reg.get("skill_name", filepath.stem)
        self.loaded_plugins[name] = reg
        self.handlers[name] = reg.get("handler")
        logger.info(f"🔌 Plugin loaded: {name} — {reg.get('description', 'no desc')}")
        return reg

    def load_all(self) -> Dict[str, Dict[str, Any]]:
        """Load all discovered plugins."""
        files = self.discover()
        if not files:
            logger.info("No plugins found in plugins/ folder.")
        for f in files:
            try:
                self.load(f)
            except Exception as e:
                logger.error(f"Plugin {f.name} failed to load: {e}")
        return self.loaded_plugins

    def reload(self) -> Dict[str, Dict[str, Any]]:
        """Clear and reload all plugins."""
        self.loaded_plugins.clear()
        self.handlers.clear()
        return self.load_all()

    def list_plugins(self) -> str:
        """Human-readable plugin list."""
        if not self.loaded_plugins:
            return "Koi plugin load nahi hua boss. plugins/ folder mein .py files daal."
        lines = [f"🔌 {len(self.loaded_plugins)} plugins loaded:"]
        for name, meta in self.loaded_plugins.items():
            lines.append(f"  • {name}: {meta.get('description', '—')}")
        return "\n".join(lines)

    def execute(self, name: str, *args) -> str:
        """Execute a loaded plugin handler."""
        handler = self.handlers.get(name)
        if not handler:
            return f"Plugin '{name}' loaded nahi hai boss."
        try:
            result = handler(*args)
            return str(result) if result else "Plugin chal gaya boss."
        except Exception as e:
            return f"Plugin '{name}' error: {str(e)[:120]}"


# Singleton
_plugin_loader: Optional[PluginLoader] = None


def get_plugin_loader() -> PluginLoader:
    global _plugin_loader
    if _plugin_loader is None:
        _plugin_loader = PluginLoader()
    return _plugin_loader
