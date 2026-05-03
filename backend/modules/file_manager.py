"""
File Manager Module — Agent-Level File Operations
Handles: find_and_explain, list_files, read_file, edit_file, search_files

Design Principles:
- Smart file search with context-based filtering
- 2-pass explanation (read → LLM explain)
- Safe file operations with backups
- Context-aware file resolution
"""

import os
import re
import fnmatch
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from groq import AsyncGroq

logger = logging.getLogger("JARVIS.FILE_MANAGER")


class FileManager:
    """
    Agent-level file manager for JARVIS.
    Smart search, file reading, explanation, and editing.
    """

    def __init__(self, config):
        self.config = config
        self.workspace = config.WORKSPACE_DIR
        self.search_dirs = config.SEARCH_DIRS
        self.code_dir = config.CODE_SAVE_DIR
        self.max_file_size_kb = config.MAX_FILE_SIZE_KB
        self.client = AsyncGroq(api_key=config.GROQ_API_KEY)
        self.file_icons = config.FILE_ICONS

    # ═══════════════════════════════════════════
    # INTERNAL: Smart File Search
    # ═══════════════════════════════════════════

    def _find_files(self, filename: str, context_keywords: List[str] = None) -> List[Tuple[Path, float]]:
        """
        Smart file search across search directories.
        Returns ranked list of (path, score) tuples.
        """
        matches = []
        filename_lower = filename.lower().strip()

        # Search all configured directories
        all_dirs = [self.workspace] + self.search_dirs
        seen = set()

        for search_dir in all_dirs:
            if not search_dir.exists():
                continue

            try:
                for root, dirs, files in os.walk(search_dir):
                    # Skip hidden dirs, node_modules, etc.
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in (
                        'node_modules', '__pycache__', 'venv', '.git', 'dist', 'build'
                    )]

                    for file in files:
                        file_lower = file.lower()
                        file_path = Path(root) / file

                        # Skip if already seen
                        real_path = file_path.resolve()
                        if real_path in seen:
                            continue
                        seen.add(real_path)

                        # Check filename match
                        name_match = fnmatch.fnmatch(file_lower, f"*{filename_lower}*")

                        if name_match:
                            score = 100  # Base score for name match

                            # Context scoring
                            if context_keywords:
                                path_str = str(file_path).lower()
                                folder_name = file_path.parent.name.lower()

                                for keyword in context_keywords:
                                    keyword_lower = keyword.lower()

                                    # Folder name matches context → boost
                                    if keyword_lower in folder_name:
                                        score += 50

                                    # Any parent folder matches
                                    if keyword_lower in path_str:
                                        score += 20

                                # Check if file content contains keywords (for extra boost)
                                if score > 100:
                                    try:
                                        content = file_path.read_text(encoding='utf-8', errors='replace')[:2000]
                                        for keyword in context_keywords:
                                            if keyword.lower() in content.lower():
                                                score += 10
                                    except Exception:
                                        pass

                            # Prefer workspace over system dirs
                            if self.workspace in file_path.parents or file_path.parent == self.workspace:
                                score += 30

                            # Penalize very deep paths
                            depth = len(file_path.parts)
                            score -= max(0, depth - 6) * 5

                            matches.append((file_path, score))

            except PermissionError:
                continue
            except Exception as e:
                logger.warning(f"Search error in {search_dir}: {e}")

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def _get_file_icon(self, filepath: Path) -> str:
        """Get emoji icon for file type."""
        if filepath.is_dir():
            return self.file_icons.get("folder", "📁")
        return self.file_icons.get(filepath.suffix.lower(), self.file_icons.get("default", "📄"))

    def _format_file_size(self, size_bytes: int) -> str:
        """Human-readable file size."""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f}KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f}MB"

    # ═══════════════════════════════════════════
    # SKILL: find_and_explain
    # ═══════════════════════════════════════════

    async def find_and_explain(self, *args) -> str:
        """
        Find file by name with optional context, then explain it.
        Trigger: [SKILL:find_and_explain:filename:context_keywords]
        Returns: File explanation from LLM.
        """
        if not args:
            return "Kaunsi file dhoondhni hai sir? Filename batao."

        filename = args[0]
        context = args[1] if len(args) > 1 else ""

        # Parse context keywords
        context_keywords = []
        if context:
            context_keywords = [kw.strip() for kw in re.split(r'[,\s]+', context) if kw.strip()]

        logger.info(f"Finding file: {filename}, context: {context_keywords}")

        # ─── PASS 1: SEARCH ───
        matches = self._find_files(filename, context_keywords)

        if not matches:
            return f"Koi bhi '{filename}' file nahi mila sir. Location specify karo?"

        # If multiple matches, pick best one (highest score)
        # If context provided and best score is high enough, use it directly
        best_match, best_score = matches[0]

        if len(matches) > 1 and best_score < 150:
            # Ambiguous — list top matches and let user choose
            top_matches = matches[:5]
            lines = [f"'{filename}' ke liye {len(matches)} results mile sir:"]
            for i, (path, score) in enumerate(top_matches, 1):
                rel = path.relative_to(self.workspace) if self.workspace in path.parents else path
                lines.append(f"{i}. {self._get_file_icon(path)} {rel} (score: {score})")
            lines.append("\nKaunsi chahiye? Number bolo ya exact path do.")
            return "\n".join(lines)

        # ─── PASS 2: READ & EXPLAIN ───
        try:
            file_size = best_match.stat().st_size
            size_kb = file_size / 1024

            if size_kb > self.max_file_size_kb:
                return f"File bahut badi hai sir ({size_kb:.0f}KB). Max {self.max_file_size_kb}KB allowed."

            content = best_match.read_text(encoding='utf-8', errors='replace')
            rel_path = best_match.relative_to(self.workspace) if self.workspace in best_match.parents else best_match

            logger.info(f"Explaining file: {best_match} ({len(content)} chars)")

            # Send to LLM for explanation
            explanation = await self._explain_with_llm(content, str(rel_path), best_match.suffix)

            return f"📄 {rel_path} — {self._format_file_size(file_size)}\n\n{explanation}"

        except Exception as e:
            logger.error(f"find_and_explain error: {e}")
            return f"File read karne mein error sir: {str(e)}"

    async def _explain_with_llm(self, content: str, filepath: str, extension: str) -> str:
        """Pass file content to LLM for explanation."""
        # Truncate if too long
        max_chars = 4000
        truncated = content[:max_chars]
        was_truncated = len(content) > max_chars

        # Detect language
        lang_map = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".jsx": "React JSX", ".tsx": "React TSX", ".java": "Java",
            ".cpp": "C++", ".c": "C", ".go": "Go", ".rs": "Rust",
            ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
            ".kt": "Kotlin", ".html": "HTML", ".css": "CSS",
            ".sql": "SQL", ".sh": "Shell", ".json": "JSON",
            ".md": "Markdown", ".yml": "YAML", ".yaml": "YAML",
        }
        language = lang_map.get(extension.lower(), "code")

        prompt = f"""Explain this {language} file in simple words:

File: {filepath}

```
{truncated}
```
{"(truncated...)" if was_truncated else ""}

Explain:
1. What does this file do? (1-2 sentences)
2. Key functions/components
3. Any important logic
Keep it brief and conversational. Mix Hindi-English (Hinglish)."""

        try:
            response = await self.client.chat.completions.create(
                model=self.config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=500,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM explanation failed: {e}")
            return f"File content:\n{truncated[:500]}..."

    # ═══════════════════════════════════════════
    # SKILL: list_files
    # ═══════════════════════════════════════════

    async def list_files(self, *args) -> str:
        """
        List files in a folder.
        Trigger: [SKILL:list_files:folder_path]
        Returns: Formatted directory listing.
        """
        folder_path = args[0] if args else str(self.workspace)

        try:
            target = Path(folder_path).expanduser().resolve()
            if not target.is_absolute():
                target = self.workspace / folder_path

            if not target.exists():
                return f"Folder nahi mila sir: {folder_path}"

            if not target.is_dir():
                return f"Yeh folder nahi hai sir, file hai: {folder_path}"

            # Get directory contents
            items = []
            dirs = []
            files = []

            for item in sorted(target.iterdir()):
                if item.name.startswith('.') and item.name not in ('.gitignore', '.env'):
                    continue

                icon = self._get_file_icon(item)

                if item.is_dir():
                    # Count files inside
                    try:
                        count = sum(1 for _ in item.iterdir() if not _.name.startswith('.'))
                        dirs.append(f"{icon} {item.name}/ ({count} items)")
                    except PermissionError:
                        dirs.append(f"{icon} {item.name}/")
                else:
                    size = self._format_file_size(item.stat().st_size)
                    files.append(f"{icon} {item.name} ({size})")

            # Build output
            rel_path = target.relative_to(self.workspace) if self.workspace in target.parents else target
            lines = [f"📂 {rel_path}/ — {len(dirs)} folders, {len(files)} files\n"]

            if dirs:
                lines.append("Folders:")
                lines.extend(f"  {d}" for d in dirs[:15])
                if len(dirs) > 15:
                    lines.append(f"  ... aur {len(dirs) - 15} folders")
                lines.append("")

            if files:
                lines.append("Files:")
                lines.extend(f"  {f}" for f in files[:20])
                if len(files) > 20:
                    lines.append(f"  ... aur {len(files) - 20} files")

            return "\n".join(lines)

        except PermissionError:
            return f"Permission denied sir: {folder_path}"
        except Exception as e:
            logger.error(f"list_files error: {e}")
            return f"Files list karne mein error sir: {str(e)}"

    # ═══════════════════════════════════════════
    # SKILL: read_file
    # ═══════════════════════════════════════════

    async def read_file(self, *args) -> str:
        """
        Read file and return content.
        Trigger: [SKILL:read_file:filepath]
        Returns: File content.
        """
        if not args:
            return "Kaunsi file read karni hai sir?"

        filepath_str = args[0]

        try:
            filepath = Path(filepath_str).expanduser().resolve()
            if not filepath.is_absolute():
                filepath = self.code_dir / filepath_str
                if not filepath.exists():
                    filepath = self.workspace / filepath_str

            if not filepath.exists():
                return f"File nahi mila sir: {filepath_str}"

            size_kb = filepath.stat().st_size / 1024
            if size_kb > self.max_file_size_kb:
                # Read first portion
                content = filepath.read_text(encoding='utf-8', errors='replace')[:5000]
                return f"⚠️ File bahut badi hai ({size_kb:.0f}KB). Pehla hissa:\n\n{content}\n\n... (truncated)"

            content = filepath.read_text(encoding='utf-8', errors='replace')
            rel_path = filepath.relative_to(self.workspace) if self.workspace in filepath.parents else filepath

            return f"📄 {rel_path} ({self._format_file_size(filepath.stat().st_size)}):\n\n{content}"

        except Exception as e:
            logger.error(f"read_file error: {e}")
            return f"File read karne mein error sir: {str(e)}"

    # ═══════════════════════════════════════════
    # SKILL: edit_file
    # ═══════════════════════════════════════════

    async def edit_file(self, *args) -> str:
        """
        Edit specific content in a file.
        Trigger: [SKILL:edit_file:filepath:old_text:new_text]
        Returns: Confirmation.
        """
        if len(args) < 3:
            return "Usage: edit_file:filepath:old_content:new_content sir."

        filepath_str = args[0]
        old_text = args[1]
        new_text = args[2] if len(args) > 2 else ""

        try:
            filepath = Path(filepath_str).expanduser().resolve()
            if not filepath.is_absolute():
                filepath = self.code_dir / filepath_str
                if not filepath.exists():
                    filepath = self.workspace / filepath_str

            if not filepath.exists():
                return f"File nahi mila sir: {filepath_str}"

            content = filepath.read_text(encoding='utf-8')

            if old_text not in content:
                return f"'{old_text}' file mein nahi mila sir. Check karo content."

            # Backup
            backup_path = filepath.with_suffix(filepath.suffix + '.backup')
            filepath.rename(backup_path)

            # Edit
            new_content = content.replace(old_text, new_text, 1)
            filepath.write_text(new_content, encoding='utf-8')

            rel_path = filepath.relative_to(self.workspace) if self.workspace in filepath.parents else filepath
            return f"✏️ {rel_path} edit ho gayi sir. Backup: {backup_path.name}"

        except Exception as e:
            logger.error(f"edit_file error: {e}")
            return f"File edit karne mein error sir: {str(e)}"

    # ═══════════════════════════════════════════
    # SKILL: search_files
    # ═══════════════════════════════════════════

    async def search_files(self, *args) -> str:
        """
        Full-text search across workspace.
        Trigger: [SKILL:search_files:query]
        Returns: Matching files with line previews.
        """
        if not args:
            return "Kya search karna hai sir?"

        query = args[0].lower()
        results = []
        max_results = 10
        max_line_preview = 80

        # Search in workspace
        search_paths = [self.workspace] + self.search_dirs
        seen = set()

        for search_dir in search_paths:
            if not search_dir.exists():
                continue

            try:
                for root, dirs, files in os.walk(search_dir):
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in (
                        'node_modules', '__pycache__', 'venv', '.git', 'dist', 'build'
                    )]

                    for file in files:
                        if file.startswith('.'):
                            continue
                        if file.endswith(('.exe', '.dll', '.so', '.dylib', '.bin', '.dat')):
                            continue

                        file_path = Path(root) / file
                        real_path = file_path.resolve()
                        if real_path in seen:
                            continue
                        seen.add(real_path)

                        # Skip very large files
                        try:
                            if file_path.stat().st_size > self.max_file_size_kb * 1024:
                                continue
                        except OSError:
                            continue

                        # Search in file
                        try:
                            content = file_path.read_text(encoding='utf-8', errors='replace')
                            if query in content.lower():
                                # Find matching lines
                                lines = content.split('\n')
                                matching_lines = []
                                for i, line in enumerate(lines, 1):
                                    if query in line.lower():
                                        preview = line.strip()[:max_line_preview]
                                        matching_lines.append(f"  L{i}: {preview}")
                                        if len(matching_lines) >= 3:
                                            break

                                rel = file_path.relative_to(search_dir) if file_path.is_relative_to(search_dir) else file_path.name
                                icon = self._get_file_icon(file_path)
                                results.append({
                                    'path': rel,
                                    'icon': icon,
                                    'lines': matching_lines,
                                    'score': len(matching_lines),
                                })

                                if len(results) >= max_results:
                                    break
                        except (UnicodeDecodeError, PermissionError):
                            continue

                    if len(results) >= max_results:
                        break

            except Exception as e:
                logger.warning(f"Search error in {search_dir}: {e}")

        if not results:
            return f"'{query}' ke liye koi results nahi mile sir."

        lines = [f"🔍 '{query}' ke liye {len(results)} files mile:\n"]
        for r in results:
            lines.append(f"{r['icon']} {r['path']}")
            lines.extend(r['lines'])
            lines.append("")

        return "\n".join(lines)


# ═══════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════

_file_manager: Optional[FileManager] = None


def get_file_manager(config) -> FileManager:
    global _file_manager
    if _file_manager is None:
        _file_manager = FileManager(config)
    return _file_manager
