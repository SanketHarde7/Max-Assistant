"""
skill_forge.py — MAX SkillForge Engine v2.0

Autonomous skill generation with full quality control.

PIPELINE:
  gap_detected
    → IntentEngine gate    (skip if CONVERSATION / CAPABILITY_QUESTION)
    → LLM code generation
    → SafetyScanner        (AST + blocked patterns)
    → DifficultyJudge      (EASY → auto-install | INTERMEDIATE/HARD → notify only)
    → DependencyResolver   (installs into backend/.venv)
    → SandboxTester        (isolated subprocess, venv python)
    → Install to plugins/
    → Hot-reload registry
    → Voice notify Sanket  ("Boss, maine X skill banayi, Y command se check karo")

KEY DESIGN DECISIONS:
  - IntentEngine gates every forge trigger — no skill built for conversational failures
  - Only EASY skills auto-install; harder ones notify Sanket to review manually
  - All pip installs go into backend/.venv (never system Python)
  - Sandbox tests run inside venv Python for accurate import resolution
  - One forge at a time (_forging lock prevents concurrent runs)
"""

import ast
import sys
import json
import time
import asyncio
import logging
import threading
import importlib.util
import subprocess
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("MAX.SKILLFORGE")


# ══════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════

# Only CONVERSATION and CAPABILITY_QUESTION responses are gated.
# INFORMATION_QUESTION failures also trigger forge (e.g. "wikipedia pe search karo").
_NO_FORGE_INTENTS = frozenset({"CAPABILITY_QUESTION", "NEGATIVE_COMMAND", "CONVERSATION"})

# Soft-gap: phrases in MAX's reply that suggest a capability gap
_GAP_SIGNALS = [
    "i can't do that", "i don't have", "not able to", "i cannot",
    "don't support", "that's not something i", "i'm not able", "can't do that",
]

# Code patterns that are NEVER allowed in generated skills
_BLOCKED_PATTERNS = [
    "os.system(", "shutil.rmtree(", "__import__(", "eval(", "exec(",
    "open('/etc", "open('C:\\\\Windows", "importlib.import_module(",
]

# Imports that push difficulty score up
_HARD_IMPORTS       = {"selenium", "playwright", "cv2", "numpy", "pandas",
                       "torch", "tensorflow", "keras", "scrapy"}
_INTERMEDIATE_IMPORTS = {"asyncio", "threading", "sqlite3", "smtplib",
                          "ftplib", "paramiko", "cryptography"}

# Code patterns that increase difficulty score
_COMPLEX_PATTERNS = ["class ", "threading.Thread", "asyncio.create_task",
                     "while True:", "for _ in range"]

# LLM prompt for skill code generation
_SKILL_GEN_PROMPT = """You are writing a Python plugin skill for MAX, a voice AI assistant.

Capability gap to fill: "{gap}"

Output ONLY valid Python. No markdown fences. No explanation. No comments.

The file MUST define exactly:
  SKILL_NAME: str    — snake_case, e.g. "wikipedia_fetch"
  DESCRIPTION: str   — one sentence what it does
  def execute(*args) -> str   — always returns non-empty string

Rules:
- No os.system(), no eval(), no exec(), no shutil.rmtree()
- Allowed imports: stdlib + httpx, psutil, pyperclip, pyautogui, webbrowser
- Wrap everything in try/except, return error string on failure, never raise
- Max 60 lines
- execute() MUST always return a non-empty string

Output ONLY the Python code:"""

# LLM prompt for test case generation
_TEST_GEN_PROMPT = """Given this Python skill:

{code}

Generate 2-3 test calls as a JSON array of argument lists.
Include: empty call, a normal call, an edge case.
Output ONLY JSON. Example: [[], ["hello"], ["hello world"]]"""


# ══════════════════════════════════════════════════════
# VENV RESOLVER
# Finds the correct Python executable inside backend/.venv
# ALL pip installs and sandbox tests use this executable.
# ══════════════════════════════════════════════════════

class VenvResolver:

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def get_python(self) -> str:
        """
        Returns path to .venv Python.
        Search order:
          1. backend/.venv/Scripts/python.exe  (Windows)
          2. backend/.venv/bin/python           (Linux / Mac)
          3. sys.executable                     (fallback — current Python)
        """
        candidates = [
            self.base_dir / ".venv" / "Scripts" / "python.exe",
            self.base_dir / ".venv" / "bin" / "python",
            self.base_dir / ".venv" / "bin" / "python3",
        ]
        for path in candidates:
            if path.exists():
                logger.debug(f"VenvResolver: using {path}")
                return str(path)

        logger.warning("VenvResolver: .venv not found, falling back to sys.executable")
        return sys.executable

    def is_venv(self) -> bool:
        return sys.prefix != sys.base_prefix


# ══════════════════════════════════════════════════════
# SAFETY SCANNER
# Two-pass: string pattern + AST structure validation
# ══════════════════════════════════════════════════════

class SafetyScanner:

    @staticmethod
    def scan(code: str) -> tuple[bool, str]:
        """Returns (is_safe, reason)"""

        # Pass 1 — blocked string patterns (fast)
        for pattern in _BLOCKED_PATTERNS:
            if pattern in code:
                return False, f"Blocked pattern: '{pattern}'"

        # Pass 2 — AST structure check
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

        has_skill_name  = False
        has_description = False
        has_execute     = False

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id == "SKILL_NAME":
                            has_skill_name = True
                        elif target.id == "DESCRIPTION":
                            has_description = True
            elif isinstance(node, ast.FunctionDef):
                if node.name == "execute":
                    has_execute = True

        if not has_skill_name:
            return False, "SKILL_NAME not defined"
        if not has_description:
            return False, "DESCRIPTION not defined"
        if not has_execute:
            return False, "execute() function missing"

        return True, "OK"


# ══════════════════════════════════════════════════════
# DIFFICULTY JUDGE
# Scores generated code 0–100.
# EASY (0-29)  → auto-install
# INTERMEDIATE (30-64) → notify Sanket, don't auto-install
# HARD (65-100) → notify Sanket, don't auto-install
# ══════════════════════════════════════════════════════

@dataclass
class DifficultyResult:
    level: str           # "EASY" | "INTERMEDIATE" | "HARD"
    score: int           # 0–100
    reasons: list[str]


class DifficultyJudge:

    HARD_THRESHOLD         = 65
    INTERMEDIATE_THRESHOLD = 30

    def judge(self, code: str) -> DifficultyResult:
        score   = 0
        reasons = []

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return DifficultyResult("HARD", 100, ["Syntax error — cannot parse"])

        # ── Lines of code (excluding comments/blanks) ──────────
        lines = [l for l in code.splitlines()
                 if l.strip() and not l.strip().startswith("#")]
        if len(lines) > 50:
            score += 20
            reasons.append(f"{len(lines)} lines (heavy logic)")
        elif len(lines) > 30:
            score += 8
            reasons.append(f"{len(lines)} lines (moderate)")

        # ── Imports ───────────────────────────────────────────
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])

        hard_found  = imports & _HARD_IMPORTS
        inter_found = imports & _INTERMEDIATE_IMPORTS

        if hard_found:
            score += 40
            reasons.append(f"Heavy deps: {', '.join(hard_found)}")
        if inter_found:
            score += 20
            reasons.append(f"Complex deps: {', '.join(inter_found)}")

        # External packages count
        stdlib   = getattr(sys, "stdlib_module_names", set())
        external = imports - stdlib - {"groq", "httpx", "psutil",
                                        "pyautogui", "pyperclip", "webbrowser"}
        if len(external) > 3:
            score += 12
            reasons.append(f"{len(external)} external packages")

        # ── Code patterns ─────────────────────────────────────
        for pattern in _COMPLEX_PATTERNS:
            if pattern in code:
                score += 8
                reasons.append(f"Uses '{pattern.strip()}'")

        # ── Function count ─────────────────────────────────────
        func_count = sum(1 for n in ast.walk(tree)
                         if isinstance(n, ast.FunctionDef))
        if func_count > 2:
            score += 10
            reasons.append(f"{func_count} function definitions")

        # ── Try/except depth ──────────────────────────────────
        try_count = sum(1 for n in ast.walk(tree) if isinstance(n, ast.Try))
        if try_count > 3:
            score += 8
            reasons.append(f"{try_count} try/except blocks")

        score = min(score, 100)

        if score >= self.HARD_THRESHOLD:
            level = "HARD"
        elif score >= self.INTERMEDIATE_THRESHOLD:
            level = "INTERMEDIATE"
        else:
            level = "EASY"

        return DifficultyResult(level, score, reasons)


# ══════════════════════════════════════════════════════
# SANDBOX TESTER
# Runs generated code in an isolated subprocess using
# the venv Python — ensures correct import resolution.
# ══════════════════════════════════════════════════════

class SandboxTester:

    def __init__(self, venv_python: str):
        self.python = venv_python

    def test(self, skill_code: str, test_cases: list) -> tuple[bool, str]:
        """Returns (all_passed, report)"""
        results = []

        for args in test_cases:
            script = f"""
import sys, os
sys.path.insert(0, '.')

{skill_code}

try:
    result = execute(*{repr(args)})
    assert isinstance(result, str), f"execute() must return str, got {{type(result).__name__}}"
    assert len(result.strip()) > 0, "execute() returned empty string"
    print("PASS:" + result[:120])
except AssertionError as e:
    print("FAIL:" + str(e))
except Exception as e:
    print("FAIL:" + str(e)[:120])
"""
            try:
                proc = subprocess.run(
                    [self.python, "-c", script],
                    capture_output=True, text=True, timeout=12
                )
                output = (proc.stdout or "").strip()

                if output.startswith("PASS:"):
                    results.append(f"  ✓ args={args}  →  {output[5:]}")
                else:
                    fail = output[5:] if output.startswith("FAIL:") \
                           else (proc.stderr or "unknown")[:120]
                    results.append(f"  ✗ args={args}  →  {fail}")
                    return False, "\n".join(results)

            except subprocess.TimeoutExpired:
                results.append(f"  ✗ args={args}  →  Timed out (>12s)")
                return False, "\n".join(results)

            except Exception as e:
                results.append(f"  ✗ args={args}  →  {e}")
                return False, "\n".join(results)

        return True, "\n".join(results)


# ══════════════════════════════════════════════════════
# SKILL FORGE ENGINE
# ══════════════════════════════════════════════════════

class SkillForgeEngine:
    """
    Orchestrates the full autonomous pipeline.

    Entry points (both called externally):
      record_unknown_skill(skill_name, user_request)
        — fired from skills dispatcher when [SKILL:xyz] tag not in registry

      record_gap(user_text, max_response)
        — fired from llm.py after every response turn
        — debounced: needs 2 consecutive gap signals

    Both check IntentEngine before forging.
    Only EASY skills auto-install. Others notify Sanket for manual review.
    """

    def __init__(self, config):
        self.config      = config
        self.base_dir    = Path(getattr(config, "BASE_DIR", "."))
        self.plugins_dir = self.base_dir / "plugins"
        self.plugins_dir.mkdir(exist_ok=True)
        self.forge_log   = self.base_dir / "skill_forge_log.jsonl"

        self._venv       = VenvResolver(self.base_dir)
        self._judge      = DifficultyJudge()
        self._sandbox    = SandboxTester(self._venv.get_python())
        self._gap_buffer : list[str] = []
        self._forging    : bool      = False

        logger.info(f"SkillForge ready — venv python: {self._venv.get_python()}")

    # ── Public entry points ────────────────────────────────────

    def record_unknown_skill(self, skill_name: str, user_request: str):
        """
        Hard trigger. LLM emitted [SKILL:something] that doesn't exist.
        This is a definite capability gap — go straight to intent gate.
        """
        gap = (f"User requested skill '{skill_name}' which does not exist. "
               f"Original request: '{user_request[:150]}'")
        logger.info(f"🔍 SkillForge hard trigger: unknown skill '{skill_name}'")
        self._trigger(gap, user_request)

    def record_gap(self, user_text: str, max_response: str):
        """
        Soft trigger. Called after every conversation turn.
        Debounced — fires only on 2 consecutive gap signals.
        Resets on any successful (non-gap) response.
        """
        if any(sig in max_response.lower() for sig in _GAP_SIGNALS):
            gap = f"User wanted: '{user_text[:120]}' — MAX couldn't handle it."
            self._gap_buffer.append(gap)
            logger.debug(f"SkillForge soft gap #{len(self._gap_buffer)}: {gap}")

            if len(self._gap_buffer) >= 2:
                self._trigger(self._gap_buffer[-1], user_text)
                self._gap_buffer.clear()
        else:
            self._gap_buffer.clear()

    # ── Internal pipeline ──────────────────────────────────────

    def _trigger(self, gap: str, user_request: str):
        if self._forging:
            logger.info("SkillForge: already running, skipping.")
            return
 
        logger.info(f"SkillForge: _trigger() called — gap='{gap[:80]}'")
 
        try:
            # Case 1: We are inside a running async event loop
            # (e.g. called from an async function via await chain)
            loop = asyncio.get_running_loop()
            loop.create_task(self._pipeline(gap, user_request))
            logger.info("SkillForge: task scheduled on running loop")
 
        except RuntimeError:
            # Case 2: No running event loop in this thread
            # (called from sync code in skills.py dispatcher)
            # Spawn a daemon thread with its own event loop.
            import threading
            t = threading.Thread(
                target=asyncio.run,
                args=(self._pipeline(gap, user_request),),
                daemon=True,
                name="SkillForge-Pipeline"
            )
            t.start()
            logger.info("SkillForge: pipeline started in background thread")

    async def _pipeline(self, gap: str, user_request: str):
        self._forging = True
        t0 = time.time()

        try:
            logger.info("⚙️  SkillForge pipeline started")

            # ── Gate 1: Intent check ──────────────────────────────
            # Don't build skills for conversational failures.
            # Only COMMAND and INFORMATION_QUESTION deserve a new skill.
            allowed = await self._intent_allows_forge(user_request)
            if not allowed:
                logger.info("SkillForge: intent gate blocked (not an actionable request)")
                return

            # ── Step 1: Generate code ─────────────────────────────
            code = await self._generate_code(gap)
            if not code:
                self._log("FAILED", gap, "LLM returned no code")
                return

            # ── Step 2: Safety scan ───────────────────────────────
            safe, reason = SafetyScanner.scan(code)
            if not safe:
                logger.error(f"SkillForge: Safety BLOCKED — {reason}")
                self._log("BLOCKED", gap, reason)
                return

            # ── Step 3: Extract skill name ────────────────────────
            skill_name = self._extract_name(code)
            if not skill_name:
                self._log("FAILED", gap, "Could not parse SKILL_NAME")
                return

            # ── Step 4: Difficulty judge ──────────────────────────
            difficulty = self._judge.judge(code)
            logger.info(
                f"SkillForge: Difficulty = {difficulty.level} "
                f"(score {difficulty.score}) — {difficulty.reasons}"
            )

            if difficulty.level != "EASY":
                # Notify Sanket — let him decide whether to install manually
                await self._notify_review_needed(skill_name, difficulty, code)
                self._log("REVIEW_NEEDED", gap,
                          f"{difficulty.level} skill '{skill_name}' — notified Sanket")
                return

            # ── Step 5: Install dependencies (into .venv) ─────────
            await self._install_deps(code)

            # ── Step 6: Generate + run sandbox tests ──────────────
            test_cases = await self._generate_tests(code)
            passed, report = self._sandbox.test(code, test_cases)

            if not passed:
                logger.error(f"SkillForge: Tests FAILED\n{report}")
                self._log("TEST_FAILED", gap, report)
                return

            logger.info(f"SkillForge: Tests passed\n{report}")

            # ── Step 7: Install plugin ────────────────────────────
            plugin_path = self.plugins_dir / f"{skill_name}.py"
            plugin_path.write_text(code, encoding="utf-8")
            logger.info(f"SkillForge: Installed → {plugin_path}")

            # ── Step 8: Hot-reload into live registry ─────────────
            self._reload_registry()

            elapsed = round(time.time() - t0, 1)
            self._log("SUCCESS", gap, f"'{skill_name}' installed in {elapsed}s")
            self._gap_buffer.clear()

            # ── Step 9: Voice notify Sanket ───────────────────────
            await self._notify_success(skill_name, elapsed)

        except Exception as e:
            logger.error(f"SkillForge: Pipeline crashed — {e}", exc_info=True)
            self._log("CRASHED", gap, str(e))
        finally:
            self._forging = False

    # ── Intent gate ────────────────────────────────────────────

    async def _intent_allows_forge(self, user_request: str) -> bool:
        """
        Returns True only if the user's request was action/info oriented.
        Blocks forge for CONVERSATION, CAPABILITY_QUESTION, NEGATIVE_COMMAND.
        """
        try:
            from modules.intent_engine import get_intent_engine
            engine = get_intent_engine(self.config)
            intent = await asyncio.wait_for(engine.classify(user_request), timeout=8.0)

            if intent.type.value in _NO_FORGE_INTENTS:
                logger.info(
                    f"SkillForge: intent gate — '{intent.type.value}' "
                    f"is not forgeable ({intent.reason})"
                )
                return False

            logger.info(f"SkillForge: intent gate passed — '{intent.type.value}'")
            return True

        except Exception as e:
            logger.warning(f"SkillForge: intent check failed ({e}), defaulting to allow")
            return True  # safe default: allow forge on uncertainty

    # ── LLM calls ─────────────────────────────────────────────

    async def _generate_code(self, gap: str) -> Optional[str]:
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=self.config.get_active_api_key())
            prompt = _SKILL_GEN_PROMPT.replace("{gap}", gap[:300])

            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=self.config.LLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.15,
                    max_tokens=700,
                ),
                timeout=30.0,
            )
            raw = resp.choices[0].message.content.strip()
            return raw.replace("```python", "").replace("```", "").strip() or None

        except Exception as e:
            logger.error(f"SkillForge: Code gen failed — {e}")
            return None

    async def _generate_tests(self, code: str) -> list:
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=self.config.get_active_api_key())
            prompt = _TEST_GEN_PROMPT.replace("{code}", code[:600])

            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=self.config.LLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=100,
                ),
                timeout=15.0,
            )
            raw = resp.choices[0].message.content.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(raw)
            return result if isinstance(result, list) else [[]]

        except Exception:
            return [[]]  # fallback: test with no args

    # ── Dependency installer (venv-aware) ──────────────────────

    async def _install_deps(self, code: str):
        """
        Parses imports from generated code.
        Installs missing packages into backend/.venv using venv's pip.
        No --break-system-packages needed inside a venv.
        """
        try:
            tree = ast.parse(code)
            packages = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        packages.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    packages.add(node.module.split(".")[0])

            stdlib   = getattr(sys, "stdlib_module_names", set())
            builtin  = {"groq", "httpx", "psutil", "pyautogui",
                        "pyperclip", "webbrowser", "subprocess", "re", "os"}
            to_check = packages - stdlib - builtin

            python = self._venv.get_python()

            for pkg in to_check:
                # Check if already importable from venv
                check = subprocess.run(
                    [python, "-c", f"import {pkg}"],
                    capture_output=True
                )
                if check.returncode != 0:
                    logger.info(f"SkillForge: pip installing '{pkg}' into .venv")
                    subprocess.run(
                        [python, "-m", "pip", "install", pkg, "-q"],
                        timeout=45, capture_output=True
                    )

        except Exception as e:
            logger.warning(f"SkillForge: Dep resolution warning — {e}")

    # ── Reload ────────────────────────────────────────────────

    def _reload_registry(self):
        try:
            from skills import get_skills_engine
            engine = get_skills_engine(self.config)
            engine.plugin_loader.reload()
            engine.skills_registry = engine._register_skills()
            logger.info("SkillForge: Registry hot-reloaded")
        except Exception as e:
            logger.error(f"SkillForge: Registry reload failed — {e}")

    # ── Notifications ──────────────────────────────────────────

    async def _notify_success(self, skill_name: str, elapsed: float):
        """
        Tells Sanket what was built and exactly how to trigger it.
        Format: "Boss, maine X skill banayi. Y command se trigger karo."
        """
        readable = skill_name.replace("_", " ")
        trigger  = f"[SKILL:{skill_name}]"
        message  = (
            f"Boss, maine {readable} skill banayi hai. "
            f"Isko trigger karne ke liye '{skill_name}' bolo. "
            f"Ek baar check kar lijiye. {elapsed} seconds mein ready hua."
        )
        logger.info(f"SkillForge notify (success): {message}")
        await self._speak(message)

    async def _notify_review_needed(
        self, skill_name: str, difficulty: DifficultyResult, code: str
    ):
        """
        INTERMEDIATE/HARD skill — Sanket ko batao, auto-install nahi.
        Saves the generated code to a review folder for manual inspection.
        """
        review_dir = self.base_dir / "skill_forge_review"
        review_dir.mkdir(exist_ok=True)
        review_path = review_dir / f"{skill_name}.py"
        review_path.write_text(code, encoding="utf-8")

        readable = skill_name.replace("_", " ")
        reasons  = "; ".join(difficulty.reasons[:2])
        message  = (
            f"Boss, maine {readable} skill try ki. "
            f"Yeh {difficulty.level} level hai — {reasons}. "
            f"Auto-install nahi kiya. skill_forge_review folder mein code hai, "
            f"manually check karke install kar sakte ho."
        )
        logger.info(f"SkillForge notify (review needed): {message}")
        await self._speak(message)

    async def _speak(self, text: str):
        try:
            from tts_engine import speak
            await speak(text)
        except Exception as e:
            logger.warning(f"SkillForge TTS failed — {e}. Message: {text}")

    # ── Utilities ─────────────────────────────────────────────

    def _extract_name(self, code: str) -> Optional[str]:
        try:
            for node in ast.walk(ast.parse(code)):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (isinstance(target, ast.Name)
                                and target.id == "SKILL_NAME"
                                and isinstance(node.value, ast.Constant)):
                            return str(node.value.value).strip()
        except Exception:
            pass
        return None

    def _log(self, status: str, gap: str, detail: str):
        entry = {
            "ts":     datetime.now().isoformat(),
            "status": status,
            "gap":    gap[:200],
            "detail": detail[:400],
        }
        try:
            with open(self.forge_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass


# ══════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════

_forge_instance: Optional[SkillForgeEngine] = None


def get_skill_forge(config) -> SkillForgeEngine:
    global _forge_instance
    if _forge_instance is None:
        _forge_instance = SkillForgeEngine(config)
    return _forge_instance
