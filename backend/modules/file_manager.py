# Path: backend/modules/file_manager.py
# Use: Handles local file reading, writing, and navigation.
"""
file_manager.py — MAX v4.0
Enhanced file management with search, list, read, edit.
Friendly tone, no 'sir' overload.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger("MAX.FILE_MANAGER")


class FileManager:
    """Advanced file management for MAX."""

    def __init__(self, config):
        self.config = config
        self.search_dirs = config.SEARCH_DIRS if hasattr(config, 'SEARCH_DIRS') else [Path.home() / "Desktop"]
        self.max_file_size_kb = config.MAX_FILE_SIZE_KB if hasattr(config, 'MAX_FILE_SIZE_KB') else 5000
        self.file_icons = getattr(config, 'FILE_ICONS', {"folder": "📁", "default": "📄"})

    # ═══════════════════════════════════════════
    # SKILL: find_and_explain
    # ═══════════════════════════════════════════

    def find_and_explain(self, *args) -> str:
        try:
            if len(args) >= 2:
                filename = args[0]
                context = args[1]
            elif len(args) == 1:
                filename = args[0]
                context = ""
            else:
                return "File ka naam aur context do boss."

            logger.info(f"Searching for: {filename} in context: {context}")

            results = self._search_for_file(filename)
            if not results:
                return f"'{filename}' kahi nahi mila boss."

            best_match = results[0]
            content = self._read_file_safe(best_match)
            icon = self._get_file_icon(best_match)

            explanation = self._explain_content(content, best_match, context)

            rel_path = self._make_relative(best_match)
            response = (
                f"📁 File: {rel_path} {icon}\n"
                f"📊 Size: {best_match.stat().st_size:,} bytes | Modified: {datetime.fromtimestamp(best_match.stat().st_mtime).strftime('%Y-%m-%d %H:%M')}\n"
                f"\n📖 Explanation:\n{explanation}\n\n"
                f"💡 Quick Actions: is file ka code review kar sakta hoon, run kar sakta hoon, ya koi bug fix kar sakta hoon."
            )

            if len(results) > 1:
                others = ", ".join(self._make_relative(r) for r in results[1:3])
                response += f"\n\n📂 Aur bhi mil gayi: {others}"

            return response

        except Exception as e:
            logger.error(f"find_and_explain error: {e}")
            return f"File dhundne mein error aaya boss: {str(e)}"

    def _search_for_file(self, filename: str) -> List[Path]:
        matches = []
        search_name = filename.lower()

        for search_dir in self.search_dirs:
            if not search_dir.exists():
                continue
            try:
                for item in search_dir.rglob("*"):
                    if item.is_file() and search_name in item.name.lower():
                        matches.append(item)
                        if len(matches) >= 5:
                            break
            except PermissionError:
                continue

        matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return matches[:5]

    def _read_file_safe(self, filepath: Path) -> str:
        try:
            size = filepath.stat().st_size
            max_size = self.max_file_size_kb * 1024
            if size > max_size:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    return f.read(max_size) + "\n\n... (file truncated, bahut bada hai boss)"
            return filepath.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def _explain_content(self, content: str, filepath: Path, context: str = "") -> str:
        lines = content.split('\n')
        total_lines = len(lines)

        ext = filepath.suffix.lower()

        explanation_parts = []

        if ext == '.py':
            imports = [l.strip() for l in lines if l.strip().startswith(('import ', 'from '))]
            functions = [l.strip() for l in lines if l.strip().startswith('def ')]
            classes = [l.strip() for l in lines if l.strip().startswith('class ')]

            explanation_parts.append(f"Python script hai boss. {total_lines} lines.")
            if imports:
                explanation_parts.append(f"Libraries: {', '.join(imports[:3])}")
            if classes:
                explanation_parts.append(f"Classes: {len(classes)}")
            if functions:
                explanation_parts.append(f"Functions: {len(functions)}")

        elif ext in ('.js', '.ts', '.jsx', '.tsx'):
            imports = [l.strip() for l in lines if 'import' in l or 'require(' in l]
            functions = [l.strip() for l in lines if 'function ' in l or 'const ' in l and '=>' in l]
            explanation_parts.append(f"JavaScript/TypeScript file hai. {total_lines} lines.")
            if imports:
                explanation_parts.append(f"Dependencies: {len(imports)} imports")
            if functions:
                explanation_parts.append(f"Functions: {len(functions)}")

        elif ext in ('.html', '.htm'):
            tags = self._extract_html_tags(content)
            explanation_parts.append(f"HTML file hai. {total_lines} lines.")
            if tags:
                explanation_parts.append(f"Main tags: {', '.join(tags[:5])}")

        elif ext == '.json':
            try:
                data = json.loads(content)
                explanation_parts.append(f"JSON file hai. Top-level keys: {list(data.keys())[:5]}")
            except Exception:
                explanation_parts.append(f"JSON file hai but invalid format boss.")

        elif ext in ('.md', '.txt'):
            words = len(content.split())
            explanation_parts.append(f"Text file hai. {words} words, {total_lines} lines.")
            first_line = lines[0].strip() if lines else ""
            if first_line:
                explanation_parts.append(f"Starts with: '{first_line[:50]}'")

        elif ext in ('.yml', '.yaml'):
            explanation_parts.append(f"YAML config file hai. {total_lines} lines.")

        elif ext in ('.css', '.scss'):
            selectors = len([l for l in lines if '{' in l])
            explanation_parts.append(f"Stylesheet hai. {selectors} selectors, {total_lines} lines.")

        else:
            explanation_parts.append(f"File hai boss. {total_lines} lines, {len(content)} characters.")
            first_line = lines[0].strip() if lines else ""
            if first_line:
                explanation_parts.append(f"First line: '{first_line[:50]}'")

        if context:
            explanation_parts.append(f"\nContext '{context}' ke hisaab se relevant sections:")
            relevant = self._find_relevant_sections(content, context)
            for section in relevant[:2]:
                explanation_parts.append(f"  - {section}")

        return "\n".join(explanation_parts)

    def _extract_html_tags(self, content: str) -> List[str]:
        tags = set()
        for match in re.finditer(r'<(\w+)', content):
            tag = match.group(1).lower()
            if tag not in ('div', 'span', 'p', 'a'):
                tags.add(tag)
        return list(tags)

    def _find_relevant_sections(self, content: str, context: str) -> List[str]:
        lines = content.split('\n')
        relevant = []
        context_lower = context.lower()
        for i, line in enumerate(lines):
            if context_lower in line.lower():
                start = max(0, i - 1)
                end = min(len(lines), i + 2)
                section = ' '.join(lines[start:end]).strip()
                if len(section) > 20:
                    relevant.append(section[:100] + "..." if len(section) > 100 else section)
        return relevant

    def _make_relative(self, filepath: Path) -> str:
        try:
            for search_dir in self.search_dirs:
                if search_dir in filepath.parents or filepath.is_relative_to(search_dir):
                    return str(filepath.relative_to(search_dir))
            return str(filepath)
        except Exception:
            return str(filepath)

    def _get_file_icon(self, filepath: Path) -> str:
        return self.file_icons.get(filepath.suffix.lower(), self.file_icons.get("default", "📄"))

    # ═══════════════════════════════════════════
    # SKILL: list_files
    # ═══════════════════════════════════════════

    def list_files(self, *args) -> str:
        try:
            folder = args[0] if args else "."
            path = Path(folder).expanduser().resolve()
            if not path.is_absolute():
                path = self.search_dirs[0] / folder
            if not path.exists():
                return f"Folder nahi mila boss: {folder}"
            if not path.is_dir():
                return f"Yeh folder nahi hai boss: {folder}"

            items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            if not items:
                return f"📁 {path.name} — folder khali hai boss."

            lines = [f"📁 {path.name}/ ({len([i for i in items if i.is_dir()])} folders, {len([i for i in items if i.is_file()])} files)"]
            for item in items[:30]:
                icon = self.file_icons.get("folder", "📁") if item.is_dir() else self._get_file_icon(item)
                size = ""
                if item.is_file():
                    try:
                        sz = item.stat().st_size
                        size = f" ({sz:,} bytes)" if sz < 1024*1024 else f" ({sz/(1024*1024):.1f} MB)"
                    except Exception:
                        pass
                lines.append(f"  {icon} {item.name}{size}")

            if len(items) > 30:
                lines.append(f"  ... aur {len(items) - 30} items aur hain boss")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"list_files error: {e}")
            return f"Files list karne mein error boss: {str(e)}"

    # ═══════════════════════════════════════════
    # SKILL: read_file
    # ═══════════════════════════════════════════

    def read_file(self, *args) -> str:
        try:
            if not args:
                return "File path do boss."
            filepath_str = args[0]
            filepath = Path(filepath_str).expanduser().resolve()
            if not filepath.is_absolute():
                filepath = self.search_dirs[0] / filepath_str
            if not filepath.exists():
                return f"File nahi mila boss: {filepath_str}"

            content = self._read_file_safe(filepath)
            lines = content.split('\n')
            total_lines = len(lines)
            icon = self._get_file_icon(filepath)

            header = f"📄 {filepath.name} {icon} ({total_lines} lines, {len(content):,} chars)"

            if total_lines > 100:
                preview = '\n'.join(lines[:50])
                return f"{header}\n\n{preview}\n\n... ({total_lines - 50} aur lines hain boss, complete file read ke liye code review kar sakta hoon)"
            else:
                return f"{header}\n\n{content}"

        except Exception as e:
            logger.error(f"read_file error: {e}")
            return f"File padhne mein error boss: {str(e)}"

    # ═══════════════════════════════════════════
    # SKILL: edit_file
    # ═══════════════════════════════════════════

    def edit_file(self, *args) -> str:
        try:
            if len(args) < 3:
                return "Usage: edit_file:filepath:old_text:new_text boss."

            filepath_str = args[0]
            old_text = args[1]
            new_text = args[2] if len(args) > 2 else ""

            filepath = Path(filepath_str).expanduser().resolve()
            if not filepath.is_absolute():
                filepath = self.search_dirs[0] / filepath_str
            if not filepath.exists():
                return f"File nahi mila boss: {filepath_str}"

            content = filepath.read_text(encoding='utf-8', errors='replace')
            if old_text not in content:
                return f"'{old_text[:30]}' text file mein nahi mila boss."

            new_content = content.replace(old_text, new_text, 1)
            backup_path = filepath.with_suffix(filepath.suffix + '.backup')
            filepath.rename(backup_path)
            filepath.write_text(new_content, encoding='utf-8')

            return f"Edit ho gayi boss. Backup: {backup_path.name}"

        except Exception as e:
            logger.error(f"edit_file error: {e}")
            return f"File edit karne mein error boss: {str(e)}"

    # ═══════════════════════════════════════════
    # SKILL: search_files
    # ═══════════════════════════════════════════

    def search_files(self, *args) -> str:
        try:
            query = " ".join(args).strip() if args else ""
            if not query:
                return "Kya search karna hai boss?"

            results = []
            for search_dir in self.search_dirs:
                if not search_dir.exists():
                    continue
                try:
                    for item in search_dir.rglob("*"):
                        if item.is_file() and query.lower() in item.name.lower():
                            results.append(item)
                            if len(results) >= 20:
                                break
                        if item.is_file() and len(results) < 20:
                            try:
                                content = item.read_text(encoding='utf-8', errors='replace')
                                if query.lower() in content.lower():
                                    results.append(item)
                            except Exception:
                                pass
                    if len(results) >= 20:
                        break
                except PermissionError:
                    continue

            if not results:
                return f"'{query}' ke liye kuch nahi mila boss."

            lines = [f"🔍 {len(results)} results for '{query}':"]
            for r in results[:10]:
                rel = self._make_relative(r)
                icon = self._get_file_icon(r)
                lines.append(f"  {icon} {rel}")
            if len(results) > 10:
                lines.append(f"  ... aur {len(results) - 10} results hain boss")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"search_files error: {e}")
            return f"Search mein error boss: {str(e)}"


# Singleton
_file_manager: Optional[FileManager] = None


def get_file_manager(config) -> FileManager:
    global _file_manager
    if _file_manager is None:
        _file_manager = FileManager(config)
    return _file_manager
