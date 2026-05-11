"""
app_indexer.py — MAX v4.0
Dynamically scans and indexes ALL installed apps on Windows.
Enables MAX to open any app by name using fuzzy matching.
Sources: Start Menu shortcuts, Program Files, Desktop, Windows Registry.
"""
import os
import json
import logging
import platform
import difflib
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("MAX.APP_INDEXER")


# ── Exe names that are never user-facing apps ──
_SKIP_KEYWORDS = {
    "uninstall", "uninst", "remove", "cleanup", "update",
    "updater", "helper", "crash", "setup", "installer",
    "elevated", "cef", "subprocess", "launcher_aux",
    "crashpad", "winstore", "squirrel", "patcher",
}


def _should_skip(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in _SKIP_KEYWORDS)


class AppIndexer:
    """
    Scans all installed applications and builds a fuzzy-searchable index.
    Cache is stored in data/app_index.json to avoid repeated slow scans.
    """

    def __init__(self, cache_file: Path):
        self.cache_file = cache_file
        # key = lowercase app name, value = full path (.lnk or .exe)
        self._index: Dict[str, str] = {}
        self._load_cache()

    # ═══════════════════════════════════════
    # Cache
    # ═══════════════════════════════════════

    def _load_cache(self):
        if self.cache_file.exists():
            try:
                raw = json.loads(self.cache_file.read_text(encoding="utf-8"))
                self._index = raw.get("index", {})
                logger.info(f"App index loaded: {len(self._index)} apps")
                return
            except Exception as e:
                logger.warning(f"App cache load failed: {e}")
        self._index = {}

    def _save_cache(self):
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(
                json.dumps({"index": self._index, "total": len(self._index)}, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"App cache save failed: {e}")

    def _add(self, name: str, path: str, overwrite: bool = False):
        key = name.lower().strip()
        if key and path and (overwrite or key not in self._index):
            self._index[key] = path

    # ═══════════════════════════════════════
    # Scanners
    # ═══════════════════════════════════════

    def _scan_start_menu(self):
        """Start Menu .lnk shortcuts — most reliable source."""
        dirs = [
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
            Path("C:/ProgramData/Microsoft/Windows/Start Menu/Programs"),
        ]
        for d in dirs:
            if not d.exists():
                continue
            try:
                for lnk in d.rglob("*.lnk"):
                    if _should_skip(lnk.stem):
                        continue
                    self._add(lnk.stem, str(lnk))
            except Exception as e:
                logger.warning(f"Start menu scan failed in {d}: {e}")

    def _scan_desktop(self):
        """User and Public desktop shortcuts."""
        for desk in [Path.home() / "Desktop", Path("C:/Users/Public/Desktop")]:
            if not desk.exists():
                continue
            try:
                for lnk in desk.glob("*.lnk"):
                    if not _should_skip(lnk.stem):
                        self._add(lnk.stem, str(lnk))
            except Exception:
                pass

    def _scan_registry(self):
        """Windows Registry App Paths — contains most installed apps."""
        if platform.system() != "Windows":
            return
        try:
            import winreg
            REG_PATHS = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
                (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            ]
            for hive, reg_path in REG_PATHS:
                try:
                    key = winreg.OpenKey(hive, reg_path)
                    i = 0
                    while True:
                        try:
                            sub_name = winreg.EnumKey(key, i)
                            sub_key  = winreg.OpenKey(key, sub_name)
                            try:
                                exe_path, _ = winreg.QueryValueEx(sub_key, "")
                                if exe_path and Path(exe_path).exists():
                                    app_name = Path(sub_name).stem
                                    if not _should_skip(app_name):
                                        self._add(app_name, exe_path)
                            except Exception:
                                pass
                            winreg.CloseKey(sub_key)
                            i += 1
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except Exception:
                    continue
        except ImportError:
            logger.info("winreg unavailable — skipping registry scan")
        except Exception as e:
            logger.warning(f"Registry scan failed: {e}")

    def _scan_program_files(self):
        """Scan Program Files for top-level executables (max 2 levels deep)."""
        dirs = [
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")),
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        ]
        for prog_dir in dirs:
            if not prog_dir.exists():
                continue
            try:
                # Only scan 2 levels deep to avoid bloating index
                for app_folder in prog_dir.iterdir():
                    if not app_folder.is_dir():
                        continue
                    for exe in app_folder.glob("*.exe"):
                        if not _should_skip(exe.stem):
                            self._add(exe.stem, str(exe))
                    # One level deeper
                    for sub in app_folder.iterdir():
                        if not sub.is_dir():
                            continue
                        for exe in sub.glob("*.exe"):
                            if not _should_skip(exe.stem):
                                self._add(exe.stem, str(exe))
            except Exception as e:
                logger.warning(f"Program files scan failed in {prog_dir}: {e}")

    # ═══════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════

    def build_index(self) -> int:
        """Full scan. Returns total app count."""
        logger.info("Building app index — scanning all sources...")
        self._index = {}

        # Priority order: Start Menu > Registry > Desktop > Program Files
        self._scan_start_menu()
        self._scan_registry()
        self._scan_desktop()
        self._scan_program_files()

        self._save_cache()
        count = len(self._index)
        logger.info(f"App index built: {count} apps found")
        return count

    def refresh_if_empty(self):
        """Auto-build on first use."""
        if not self._index:
            self.build_index()

    def find_app(self, query: str) -> Optional[Tuple[str, str]]:
        """
        Find best matching app for query string.
        Returns (matched_name, full_path) or None.

        Priority:
          1. Exact match
          2. Starts-with match
          3. Contains match
          4. Fuzzy match (cutoff 0.65)
        """
        self.refresh_if_empty()
        q = query.lower().strip()
        if not q:
            return None

        # 1. Exact
        if q in self._index:
            return (q, self._index[q])

        # 2. Starts-with
        for name, path in self._index.items():
            if name.startswith(q) or q.startswith(name):
                return (name, path)

        # 3. Contains
        for name, path in self._index.items():
            if q in name:
                return (name, path)

        # 4. Fuzzy
        matches = difflib.get_close_matches(q, self._index.keys(), n=1, cutoff=0.65)
        if matches:
            name = matches[0]
            return (name, self._index[name])

        return None

    def list_apps(self, query: str = "", limit: int = 30) -> List[str]:
        """List indexed app names, filtered by query."""
        self.refresh_if_empty()
        if query:
            q = query.lower()
            return sorted(n for n in self._index if q in n)[:limit]
        return sorted(self._index.keys())[:limit]

    def get_stats(self) -> dict:
        return {
            "total": len(self._index),
            "cache": str(self.cache_file),
            "cached": self.cache_file.exists(),
        }


# ══════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════

_indexer: Optional[AppIndexer] = None


def get_app_indexer(config) -> AppIndexer:
    global _indexer
    if _indexer is None:
        cache_path = Path(config.DATA_DIR) / "app_index.json"
        _indexer = AppIndexer(cache_path)
        _indexer.refresh_if_empty()
    return _indexer
