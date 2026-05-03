"""
Code Engine Module — Agent-Level Code Generation & Execution
Handles: write_code, run_code, code_review, fix_code, project_scaffold

Design Principles:
- Clean code via separate LLM call
- Automatic language detection
- Secure execution with timeouts
- Error recovery and auto-fix attempts
"""

import os
import re
import sys
import ast
import json
import time
import logging
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List

# Groq for code generation
from groq import AsyncGroq

logger = logging.getLogger("JARVIS.CODE_ENGINE")


class CodeEngine:
    """
    Agent-level code engine for JARVIS.
    Generates, executes, reviews, and fixes code.
    """

    def __init__(self, config):
        self.config = config
        self.workspace = config.WORKSPACE_DIR
        self.code_dir = config.CODE_SAVE_DIR
        self.client = AsyncGroq(api_key=config.GROQ_API_KEY)
        self.languages = config.CODE_LANGUAGES
        self.timeout = config.AGENT_CODE_TIMEOUT
        self.max_file_size_kb = config.MAX_FILE_SIZE_KB

    # ═══════════════════════════════════════════
    # INTERNAL: Code Generation via LLM
    # ═══════════════════════════════════════════

    async def _generate_code_with_llm(self, description: str, language: str, extra_context: str = "") -> str:
        """
        Generate clean code via separate LLM call.
        This is the core — all code comes from here.
        """
        system_prompt = f"""You are JARVIS Code Generator — an expert programmer.
Rules:
- Write ONLY code, no explanations, no markdown code blocks
- Code must be complete, runnable, and well-commented
- Use best practices and proper error handling
- Keep it concise but fully functional
- Do NOT include ``` or any markdown formatting
- Do NOT write a main() function unless explicitly asked
- Include brief docstring/comments explaining what the code does
"""
        user_prompt = f"Write {language} code for: {description}"
        if extra_context:
            user_prompt += f"\n\nAdditional context: {extra_context}"

        try:
            response = await self.client.chat.completions.create(
                model=self.config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # Low temp for consistent code
                max_tokens=2000,
            )
            code = response.choices[0].message.content.strip()
            # Remove markdown code blocks if LLM included them
            code = self._strip_markdown_code_blocks(code)
            return code
        except Exception as e:
            logger.error(f"Code generation LLM call failed: {e}")
            return f"# Error generating code: {e}"

    def _strip_markdown_code_blocks(self, text: str) -> str:
        """Remove ```language and ``` markers from code."""
        # Remove opening ```language
        text = re.sub(r'^```\w*\n', '', text, flags=re.MULTILINE)
        # Remove closing ```
        text = re.sub(r'\n```\s*$', '', text, flags=re.MULTILINE)
        # Remove inline ```
        text = text.replace('```', '')
        return text.strip()

    def _detect_language(self, hint: str) -> str:
        """Auto-detect programming language from hint."""
        hint_lower = hint.lower().strip()

        # Direct language mentions
        lang_map = {
            "python": "python", "py": "python",
            "javascript": "javascript", "js": "javascript",
            "typescript": "typescript", "ts": "typescript",
            "java": "java",
            "c++": "cpp", "cpp": "cpp",
            "c": "c",
            "go": "go", "golang": "go",
            "rust": "rust", "rs": "rust",
            "ruby": "ruby", "rb": "ruby",
            "php": "php",
            "swift": "swift",
            "kotlin": "kotlin", "kt": "kotlin",
            "html": "html",
            "css": "css",
            "sql": "sql",
            "bash": "bash", "shell": "bash", "sh": "bash",
            "powershell": "powershell", "ps1": "powershell",
            "react": "javascript",
            "nodejs": "javascript", "node": "javascript",
        }

        for key, lang in lang_map.items():
            if key in hint_lower:
                return lang

        # Check for file extension in hint
        ext_match = re.search(r'\.(\w+)$', hint_lower)
        if ext_match:
            ext = ext_match.group(1)
            for lang, lang_ext in self.languages.items():
                if lang_ext == f".{ext}":
                    return lang

        # Default to python
        return "python"

    def _generate_filename(self, description: str, language: str) -> str:
        """Generate meaningful filename from description."""
        # Clean description
        clean = re.sub(r'[^\w\s-]', '', description.lower().strip())
        clean = re.sub(r'\s+', '_', clean)

        # Limit length
        if len(clean) > 50:
            clean = clean[:50]

        # Get extension
        ext = self.languages.get(language, ".py")

        return f"{clean}{ext}"

    def _get_unique_filepath(self, filename: str) -> Path:
        """Get unique filepath, append number if exists."""
        filepath = self.code_dir / filename
        if not filepath.exists():
            return filepath

        stem = filepath.stem
        ext = filepath.suffix
        counter = 1
        while True:
            new_name = f"{stem}_{counter}{ext}"
            new_path = self.code_dir / new_name
            if not new_path.exists():
                return new_path
            counter += 1

    def _save_code_file(self, code: str, filepath: Path) -> str:
        """Save code to file, return the path."""
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(code, encoding='utf-8')
            return str(filepath)
        except Exception as e:
            logger.error(f"Failed to save code file: {e}")
            raise

    # ═══════════════════════════════════════════
    # SKILL: write_code
    # ═══════════════════════════════════════════

    async def write_code(self, *args) -> str:
        """
        Generate code and save to file.
        Trigger: [SKILL:write_code:language:description]
        Returns: Confirmation message with filepath.
        """
        try:
            # Parse arguments
            if len(args) >= 2:
                language_hint = args[0]
                description = args[1]
            elif len(args) == 1:
                # Auto-detect from description
                language_hint = args[0]
                description = args[0]
            else:
                return "Please provide what code to write, sir."

            # Detect language
            language = self._detect_language(language_hint)

            # Generate filename
            filename = self._generate_filename(description, language)
            filepath = self._get_unique_filepath(filename)

            # Generate code via LLM
            code = await self._generate_code_with_llm(description, language)

            if code.startswith("# Error"):
                return "Code generation failed sir. Please try again with more details."

            # Save to file
            saved_path = self._save_code_file(code, filepath)
            rel_path = Path(saved_path).relative_to(self.workspace)

            logger.info(f"Code saved: {saved_path} ({len(code)} chars)")

            return f"Code likh diya sir, {rel_path} mein save ho gayi."

        except Exception as e:
            logger.error(f"write_code error: {e}")
            return f"Code writing mein error aaya sir: {str(e)}"

    # ═══════════════════════════════════════════
    # SKILL: run_code
    # ═══════════════════════════════════════════

    async def run_code(self, *args) -> str:
        """
        Execute code file safely with timeout.
        Trigger: [SKILL:run_code:filepath]
        Returns: Output or error message.
        """
        if not args:
            return "Please provide the file path to run, sir."

        filepath_str = args[0]

        try:
            # Resolve path
            filepath = Path(filepath_str).expanduser().resolve()
            if not filepath.is_absolute():
                # Try relative to code_dir first, then workspace
                filepath = self.code_dir / filepath_str
                if not filepath.exists():
                    filepath = self.workspace / filepath_str

            if not filepath.exists():
                return f"File nahi mila sir: {filepath_str}"

            # Check file size
            size_kb = filepath.stat().st_size / 1024
            if size_kb > self.max_file_size_kb:
                return f"File bahut badi hai sir ({size_kb:.0f}KB). Max {self.max_file_size_kb}KB allowed."

            language = self._detect_language(filepath.suffix)
            code = filepath.read_text(encoding='utf-8')

            result = await self._execute_code(code, language, filepath)
            return result

        except Exception as e:
            logger.error(f"run_code error: {e}")
            return f"Code run karne mein error aaya sir: {str(e)}"

    async def _execute_code(self, code: str, language: str, filepath: Path) -> str:
        """Execute code based on language with proper runner."""
        try:
            if language == "python":
                return await self._run_python_code(code, filepath)
            elif language in ("javascript", "typescript"):
                return await self._run_nodejs_code(code, filepath)
            elif language in ("bash", "shell", "powershell"):
                return await self._run_shell_code(code, filepath)
            elif language == "go":
                return await self._run_go_code(code, filepath)
            elif language == "rust":
                return await self._run_rust_code(code, filepath)
            elif language == "java":
                return await self._run_java_code(code, filepath)
            elif language == "c" or language == "cpp":
                return await self._run_c_cpp_code(code, filepath)
            else:
                return f"{language} ke liye runner abhi available nahi hai sir. Sirf execute kar sakta hoon: python, javascript, bash, go, rust, java, c, cpp."
        except Exception as e:
            return f"Execution error: {str(e)[:200]}"

    async def _run_python_code(self, code: str, filepath: Path) -> str:
        """Execute Python code safely."""
        # Quick syntax check
        try:
            ast.parse(code)
        except SyntaxError as e:
            return f"Syntax Error sir: Line {e.lineno}: {e.msg}"

        # Run with timeout
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(filepath),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
            output = stdout.decode('utf-8', errors='replace').strip()
            error = stderr.decode('utf-8', errors='replace').strip()

            if proc.returncode == 0:
                if output:
                    return f"Output sir:\n{output[:500]}"
                return "Code successfully run ho gaya sir. Koi output nahi tha."
            else:
                err_msg = error[:300] if error else "Unknown error"
                return f"Error sir:\n{err_msg}"

        except asyncio.TimeoutError:
            proc.kill()
            return f"Code {self.timeout}s se zyada time le raha tha sir. Timeout kar diya."

    async def _run_nodejs_code(self, code: str, filepath: Path) -> str:
        """Execute Node.js code."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "node", str(filepath),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
            output = stdout.decode('utf-8', errors='replace').strip()
            error = stderr.decode('utf-8', errors='replace').strip()

            if proc.returncode == 0:
                return f"Output sir:\n{output[:500]}" if output else "Code successfully run ho gaya sir."
            else:
                return f"Error sir:\n{error[:300]}"

        except FileNotFoundError:
            return "Node.js installed nahi hai sir. Please install Node.js first."
        except asyncio.TimeoutError:
            proc.kill()
            return f"Code timeout ho gaya sir ({self.timeout}s)."

    async def _run_shell_code(self, code: str, filepath: Path) -> str:
        """Execute shell/bash script."""
        try:
            proc = await asyncio.create_subprocess_shell(
                code if code else f"bash {filepath}",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.workspace,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
            output = stdout.decode('utf-8', errors='replace').strip()
            error = stderr.decode('utf-8', errors='replace').strip()

            if proc.returncode == 0:
                return f"Output sir:\n{output[:500]}" if output else "Command run ho gayi sir."
            else:
                return f"Error sir:\n{error[:300]}"

        except asyncio.TimeoutError:
            proc.kill()
            return f"Command timeout ho gayi sir ({self.timeout}s)."

    async def _run_go_code(self, code: str, filepath: Path) -> str:
        """Execute Go code."""
        try:
            # Run directly with 'go run'
            proc = await asyncio.create_subprocess_exec(
                "go", "run", str(filepath),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=filepath.parent,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
            output = stdout.decode('utf-8', errors='replace').strip()
            error = stderr.decode('utf-8', errors='replace').strip()

            if proc.returncode == 0:
                return f"Output sir:\n{output[:500]}" if output else "Go code run ho gaya sir."
            else:
                return f"Go error sir:\n{error[:300]}"

        except FileNotFoundError:
            return "Go compiler installed nahi hai sir. 'go' command nahi mila."
        except asyncio.TimeoutError:
            proc.kill()
            return f"Go code timeout ho gaya sir ({self.timeout}s)."

    async def _run_rust_code(self, code: str, filepath: Path) -> str:
        """Execute Rust code using rustc or cargo script."""
        try:
            # Use rustc to compile and run
            exe_path = filepath.with_suffix('')
            compile_proc = await asyncio.create_subprocess_exec(
                "rustc", str(filepath), "-o", str(exe_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _, compile_err = await asyncio.wait_for(compile_proc.communicate(), timeout=30)

            if compile_proc.returncode != 0:
                return f"Rust compile error sir:\n{compile_err.decode()[:300]}"

            # Run compiled binary
            run_proc = await asyncio.create_subprocess_exec(
                str(exe_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                run_proc.communicate(), timeout=self.timeout
            )

            # Cleanup
            if exe_path.exists():
                exe_path.unlink()

            output = stdout.decode('utf-8', errors='replace').strip()
            if run_proc.returncode == 0:
                return f"Output sir:\n{output[:500]}" if output else "Rust code run ho gaya sir."
            else:
                return f"Runtime error sir:\n{stderr.decode()[:300]}"

        except FileNotFoundError:
            return "Rust compiler (rustc) installed nahi hai sir."
        except asyncio.TimeoutError:
            return f"Rust code timeout ho gaya sir ({self.timeout}s)."

    async def _run_java_code(self, code: str, filepath: Path) -> str:
        """Execute Java code."""
        try:
            # Compile
            compile_proc = await asyncio.create_subprocess_exec(
                "javac", str(filepath),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=filepath.parent,
            )
            _, compile_err = await asyncio.wait_for(compile_proc.communicate(), timeout=30)

            if compile_proc.returncode != 0:
                return f"Java compile error sir:\n{compile_err.decode()[:300]}"

            # Run
            class_name = filepath.stem
            run_proc = await asyncio.create_subprocess_exec(
                "java", class_name,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=filepath.parent,
            )
            stdout, stderr = await asyncio.wait_for(
                run_proc.communicate(), timeout=self.timeout
            )

            output = stdout.decode('utf-8', errors='replace').strip()
            if run_proc.returncode == 0:
                return f"Output sir:\n{output[:500]}" if output else "Java code run ho gaya sir."
            else:
                return f"Runtime error sir:\n{stderr.decode()[:300]}"

        except FileNotFoundError:
            return "Java (javac/java) installed nahi hai sir."
        except asyncio.TimeoutError:
            return f"Java code timeout ho gaya sir ({self.timeout}s)."

    async def _run_c_cpp_code(self, code: str, filepath: Path) -> str:
        """Execute C/C++ code."""
        try:
            compiler = "g++" if filepath.suffix in ('.cpp', '.cxx', '.cc') else "gcc"
            exe_path = filepath.with_suffix('.exe' if sys.platform == 'win32' else '')

            # Compile
            compile_proc = await asyncio.create_subprocess_exec(
                compiler, str(filepath), "-o", str(exe_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _, compile_err = await asyncio.wait_for(compile_proc.communicate(), timeout=30)

            if compile_proc.returncode != 0:
                return f"{compiler.upper()} compile error sir:\n{compile_err.decode()[:300]}"

            # Run
            run_proc = await asyncio.create_subprocess_exec(
                str(exe_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                run_proc.communicate(), timeout=self.timeout
            )

            # Cleanup
            if exe_path.exists():
                exe_path.unlink()

            output = stdout.decode('utf-8', errors='replace').strip()
            if run_proc.returncode == 0:
                return f"Output sir:\n{output[:500]}" if output else "Code run ho gaya sir."
            else:
                return f"Runtime error sir:\n{stderr.decode()[:300]}"

        except FileNotFoundError:
            return f"{compiler.upper()} compiler installed nahi hai sir."
        except asyncio.TimeoutError:
            return f"C/C++ code timeout ho gaya sir ({self.timeout}s)."

    # ═══════════════════════════════════════════
    # SKILL: code_review
    # ═══════════════════════════════════════════

    async def code_review(self, *args) -> str:
        """
        Analyze code and provide review.
        Trigger: [SKILL:code_review:filepath]
        Returns: Review findings.
        """
        if not args:
            return "Please provide the file to review, sir."

        filepath_str = args[0]

        try:
            filepath = Path(filepath_str).expanduser().resolve()
            if not filepath.is_absolute():
                filepath = self.code_dir / filepath_str
                if not filepath.exists():
                    filepath = self.workspace / filepath_str

            if not filepath.exists():
                return f"File nahi mila sir: {filepath_str}"

            code = filepath.read_text(encoding='utf-8')
            if len(code) > self.max_file_size_kb * 1024:
                return f"File bahut badi hai sir. Review ke liye choti file do."

            # Local static analysis
            language = self._detect_language(filepath.suffix)
            issues = self._static_analysis(code, language)

            # LLM review
            review = await self._llm_code_review(code, language, filepath.name)

            response = f"Code review for {filepath.name}:\n\n{review}"
            if issues:
                response += f"\n\nStatic analysis issues:\n" + "\n".join(issues[:5])

            return response

        except Exception as e:
            logger.error(f"code_review error: {e}")
            return f"Review mein error aaya sir: {str(e)}"

    def _static_analysis(self, code: str, language: str) -> List[str]:
        """Basic static analysis for common issues."""
        issues = []

        if language == "python":
            # Check syntax
            try:
                ast.parse(code)
            except SyntaxError as e:
                issues.append(f"Syntax error at line {e.lineno}: {e.msg}")

            # Check for common issues
            lines = code.split('\n')
            for i, line in enumerate(lines, 1):
                if 'eval(' in line and not line.strip().startswith('#'):
                    issues.append(f"Line {i}: eval() use — security risk")
                if 'exec(' in line and not line.strip().startswith('#'):
                    issues.append(f"Line {i}: exec() use — security risk")
                if 'password' in line.lower() and '=' in line:
                    issues.append(f"Line {i}: Hardcoded password detected")
                if 'TODO' in line:
                    issues.append(f"Line {i}: TODO found — incomplete implementation")
                if 'FIXME' in line:
                    issues.append(f"Line {i}: FIXME found — known issue")

            if 'if __name__' not in code and len(lines) > 20:
                issues.append("Missing 'if __name__ == main' guard — code runs on import")

            if 'try:' not in code and ('open(' in code or 'requests.' in code):
                issues.append("No error handling for I/O operations")

        return issues

    async def _llm_code_review(self, code: str, language: str, filename: str) -> str:
        """Get LLM-based code review."""
        prompt = f"""Review this {language} code file '{filename}':

```
{code[:3000]}
```

Provide a brief review covering:
1. Code quality (1-2 lines)
2. Any bugs or issues
3. Suggestions for improvement
Keep it concise — max 5 bullet points."""

        try:
            response = await self.client.chat.completions.create(
                model=self.config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=500,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return "LLM review unavailable sir. Static analysis se kaam chala lo."

    # ═══════════════════════════════════════════
    # SKILL: fix_code
    # ═══════════════════════════════════════════

    async def fix_code(self, *args) -> str:
        """
        Fix specific issue in code file.
        Trigger: [SKILL:fix_code:filepath:issue_description]
        Returns: Confirmation of fix.
        """
        if len(args) < 2:
            return "Usage: fix_code:filepath:issue_description sir."

        filepath_str = args[0]
        issue = args[1] if len(args) > 1 else "fix issues"

        try:
            filepath = Path(filepath_str).expanduser().resolve()
            if not filepath.is_absolute():
                filepath = self.code_dir / filepath_str
                if not filepath.exists():
                    filepath = self.workspace / filepath_str

            if not filepath.exists():
                return f"File nahi mila sir: {filepath_str}"

            code = filepath.read_text(encoding='utf-8')
            language = self._detect_language(filepath.suffix)

            # Generate fix via LLM
            fixed_code = await self._generate_fix(code, language, issue)

            if fixed_code.startswith("# Error") or fixed_code == code:
                return "Fix generate nahi ho paya sir. Koi improvement nahi mila."

            # Backup original
            backup_path = filepath.with_suffix(filepath.suffix + '.backup')
            filepath.rename(backup_path)

            # Save fixed code
            self._save_code_file(fixed_code, filepath)

            return f"Code fix kar diya sir. Backup: {backup_path.name}"

        except Exception as e:
            logger.error(f"fix_code error: {e}")
            return f"Code fix karne mein error sir: {str(e)}"

    async def _generate_fix(self, code: str, language: str, issue: str) -> str:
        """Generate fixed code via LLM."""
        prompt = f"""Fix this {language} code for the issue: {issue}

Original code:
```
{code[:3000]}
```

Return ONLY the fixed code, no explanations, no markdown blocks."""

        try:
            response = await self.client.chat.completions.create(
                model=self.config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            return self._strip_markdown_code_blocks(response.choices[0].message.content.strip())
        except Exception:
            return code

    # ═══════════════════════════════════════════
    # SKILL: project_scaffold
    # ═══════════════════════════════════════════

    async def project_scaffold(self, *args) -> str:
        """
        Create project skeleton from template.
        Trigger: [SKILL:project_scaffold:type:name]
        Returns: Confirmation with project path.
        """
        if len(args) < 1:
            return "Project type aur name dono chahiye sir. Example: 'react todo-app'"

        project_type = args[0].lower().strip()
        project_name = args[1] if len(args) > 1 else f"my-{project_type}-project"

        # Clean name
        project_name = re.sub(r'[^\w-]', '', project_name).lower()

        if project_type not in self.config.PROJECT_TEMPLATES:
            available = ", ".join(self.config.PROJECT_TEMPLATES.keys())
            return f"Template nahi mila sir. Available: {available}"

        try:
            template = self.config.PROJECT_TEMPLATES[project_type]
            project_dir = self.code_dir / project_name

            if project_dir.exists():
                return f"{project_name} already exists sir. Doosra naam do."

            # Create directories
            for dir_path in template.get("dirs", []):
                (project_dir / dir_path).mkdir(parents=True, exist_ok=True)

            # Create files with template substitution
            for file_path, content in template.get("files", {}).items():
                full_path = project_dir / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                filled_content = content.replace("{{name}}", project_name)
                full_path.write_text(filled_content, encoding='utf-8')

            logger.info(f"Project scaffolded: {project_dir}")

            # Count files
            file_count = sum(1 for _ in project_dir.rglob('*') if _.is_file())
            return f"{project_type.upper()} project '{project_name}' ready hai sir. {file_count} files banayi."

        except Exception as e:
            logger.error(f"project_scaffold error: {e}")
            return f"Project scaffold karne mein error sir: {str(e)}"


# Singleton
import asyncio

_code_engine: Optional[CodeEngine] = None


def get_code_engine(config) -> CodeEngine:
    global _code_engine
    if _code_engine is None:
        _code_engine = CodeEngine(config)
    return _code_engine
