"""
Agent Core Module — Task Planning & Multi-Step Execution
Makes JARVIS truly agentic:
- Task decomposition (break complex tasks into steps)
- Multi-step execution with error recovery
- Context learning (remembers user corrections)
- Self-correction (fixes its own mistakes)

This is the brain behind the agent-level behavior.
"""

import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict

from groq import AsyncGroq

logger = logging.getLogger("JARVIS.AGENT")


@dataclass
class TaskStep:
    """Single step in a multi-step task plan."""
    step_number: int
    description: str
    skill: str  # which skill to use
    params: List[str]
    status: str = "pending"  # pending, running, completed, failed
    result: str = ""
    retry_count: int = 0


@dataclass
class TaskPlan:
    """Complete task plan with multiple steps."""
    task_id: str
    original_request: str
    steps: List[TaskStep]
    current_step: int = 0
    status: str = "pending"  # pending, running, completed, failed
    created_at: str = ""
    completed_at: str = ""
    summary: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "original_request": self.original_request,
            "status": self.status,
            "current_step": self.current_step,
            "total_steps": len(self.steps),
            "steps": [
                {
                    "step_number": s.step_number,
                    "description": s.description,
                    "skill": s.skill,
                    "params": s.params,
                    "status": s.status,
                    "result": s.result,
                    "retry_count": s.retry_count,
                }
                for s in self.steps
            ],
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "summary": self.summary,
        }


class TaskPlanner:
    """
    Decomposes complex user requests into actionable steps.
    Uses LLM for intelligent task breakdown.
    """

    PLANNING_PROMPT = """You are JARVIS Task Planner. Break down the user's request into clear steps.
Each step must use ONE skill only.

Available skills and their parameters:
- write_code:language:description — Write code file
- run_code:filepath — Run a code file  
- code_review:filepath — Review code
- find_and_explain:filename:context — Find and explain a file
- list_files:folder — List folder contents
- read_file:filepath — Read file content
- edit_file:filepath:old_text:new_text — Edit file
- project_scaffold:type:name — Create project structure
- search:query — Web search
- open_app:name — Open application
- web_open:url — Open URL

User request: {request}

Respond in this EXACT format:
STEP 1: [skill_name:param1:param2] - Brief description
STEP 2: [skill_name:param1] - Brief description
...

Keep steps minimal and sequential. Maximum 5 steps.
If request is simple (1 step), just return 1 step.
"""

    def __init__(self, config):
        self.config = config
        self.client = AsyncGroq(api_key=config.GROQ_API_KEY)
        self.max_steps = config.AGENT_MAX_STEPS

    async def create_plan(self, user_request: str) -> TaskPlan:
        """
        Create a task plan from user request.
        Uses LLM to decompose complex requests.
        """
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Simple requests — single step, no LLM needed
        simple_skills = self._detect_simple_skill(user_request)
        if simple_skills:
            steps = [TaskStep(
                step_number=1,
                description=f"Execute: {user_request}",
                skill=skill_name,
                params=params,
            ) for skill_name, params in simple_skills]
            return TaskPlan(
                task_id=task_id,
                original_request=user_request,
                steps=steps,
            )

        # Complex request — use LLM to plan
        try:
            plan_text = await self._llm_plan(user_request)
            steps = self._parse_plan(plan_text)
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            # Fallback: single step with the original request
            steps = [TaskStep(
                step_number=1,
                description=user_request,
                skill="search",
                params=[user_request],
            )]

        return TaskPlan(
            task_id=task_id,
            original_request=user_request,
            steps=steps[:self.max_steps],
        )

    def _detect_simple_skill(self, request: str) -> Optional[List[Tuple[str, List[str]]]]:
        """
        Quick pattern matching for simple requests.
        Returns list of (skill_name, params) or None.
        """
        r = request.lower().strip()
        results = []

        # Code writing patterns
        code_patterns = [
            (r'(?:code|script|program)\s+(?:likh|bana|write)\s+(?:kar|do)?\s*(?:python|js|javascript|java|go|rust|c\+\+|cpp|html|css)?\s*(?:mein|main|for)?\s*(.+)', 'write_code'),
            (r'(?:python|js|javascript|java|go|rust|c\+\+|cpp|html|css)\s+(?:code|script|program)\s+(?:likh|bana|write)', 'write_code'),
            (r'(.+)\s+(?:ka|ki)\s+(?:code|script|program)\s+(?:likh|bana)', 'write_code'),
        ]

        for pattern, skill in code_patterns:
            match = re.search(pattern, r)
            if match:
                # Try to detect language
                lang = "python"  # default
                lang_hints = {
                    'python': 'python', 'py': 'python',
                    'javascript': 'javascript', 'js': 'javascript',
                    'java': 'java', 'go': 'go', 'golang': 'go',
                    'rust': 'rust', 'c++': 'cpp', 'cpp': 'cpp',
                    'html': 'html', 'css': 'css', 'typescript': 'typescript',
                }
                for hint, detected in lang_hints.items():
                    if hint in r:
                        lang = detected
                        break
                desc = match.group(1) if match.lastindex else match.group(0)
                results.append((skill, [lang, desc.strip()]))
                return results

        # File finding patterns
        file_patterns = [
            (r'(.+)\s+(?:ki|ka|ke)\s+(.+)\s+(?:samjha|samjhao|explain|dekho|dikhao)', 'find_and_explain'),
            (r'(?:samjha|samjhao|explain)\s+(.+)', 'find_and_explain'),
        ]
        for pattern, skill in file_patterns:
            match = re.search(pattern, r)
            if match:
                if skill == 'find_and_explain' and match.lastindex >= 2:
                    results.append((skill, [match.group(2).strip(), match.group(1).strip()]))
                else:
                    filename = match.group(1).strip()
                    # Check if context is in the filename (e.g., "linkedin main.py")
                    parts = filename.split()
                    if len(parts) > 1:
                        # Last part is likely the filename
                        results.append((skill, [parts[-1], ' '.join(parts[:-1])]))
                    else:
                        results.append((skill, [filename, ""]))
                return results

        # Project scaffold patterns
        scaffold_patterns = [
            (r'(?:ek|a|an)\s+(react|python|node|fastapi)\s+(?:project|app|application)', 'project_scaffold'),
        ]
        for pattern, skill in scaffold_patterns:
            match = re.search(pattern, r)
            if match:
                proj_type = match.group(1)
                # Extract name from request
                name = "my-project"
                name_match = re.search(r'(?:named|called|name)\s+([\w-]+)', r)
                if name_match:
                    name = name_match.group(1)
                results.append((skill, [proj_type, name]))
                return results

        # List files patterns
        list_patterns = [
            (r'(?:files|folder|directory|contents)\s+(?:dikhao|dikhawo|list|show|dekho)', 'list_files'),
        ]
        for pattern, skill in list_patterns:
            if re.search(pattern, r):
                results.append((skill, [""]))
                return results

        return None

    async def _llm_plan(self, request: str) -> str:
        """Get plan from LLM."""
        prompt = self.PLANNING_PROMPT.replace("{request}", request)

        response = await self.client.chat.completions.create(
            model=self.config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()

    def _parse_plan(self, plan_text: str) -> List[TaskStep]:
        """Parse LLM plan output into TaskStep objects."""
        steps = []
        step_pattern = re.compile(
            r'STEP\s+(\d+)\s*:\s*\[([a-zA-Z_]+)(?::([^\]]*))?\]\s*[-:]\s*(.+)',
            re.IGNORECASE
        )

        for match in step_pattern.finditer(plan_text):
            step_num = int(match.group(1))
            skill = match.group(2).lower()
            params_str = match.group(3) or ""
            description = match.group(4).strip()

            params = [p.strip() for p in params_str.split(":") if p.strip()]

            steps.append(TaskStep(
                step_number=step_num,
                description=description,
                skill=skill,
                params=params,
            ))

        if not steps:
            # Fallback: treat entire response as one step
            steps.append(TaskStep(
                step_number=1,
                description="Execute request",
                skill="search",
                params=[plan_text],
            ))

        return steps


class AgentCore:
    """
    Central agent orchestrator.
    Manages task planning, execution, learning, and self-correction.
    """

    def __init__(self, config):
        self.config = config
        self.planner = TaskPlanner(config)
        self.learned_corrections: Dict[str, str] = {}
        self.task_history: List[Dict] = []
        self._load_learned_data()

    def _load_learned_data(self):
        """Load previously learned corrections."""
        learn_file = Path(self.config.DATA_DIR) / "agent_learned.json"
        if learn_file.exists():
            try:
                data = json.loads(learn_file.read_text())
                self.learned_corrections = data.get("corrections", {})
                self.task_history = data.get("task_history", [])[-50:]  # Keep last 50
            except Exception as e:
                logger.warning(f"Could not load learned data: {e}")

    def _save_learned_data(self):
        """Persist learned data."""
        learn_file = Path(self.config.DATA_DIR) / "agent_learned.json"
        try:
            learn_file.write_text(json.dumps({
                "corrections": self.learned_corrections,
                "task_history": self.task_history[-100:],  # Keep last 100
                "last_updated": datetime.now().isoformat(),
            }, indent=2))
        except Exception as e:
            logger.error(f"Could not save learned data: {e}")

    async def plan_and_execute(self, user_request: str) -> TaskPlan:
        """
        Full pipeline: Plan → Execute → Learn.
        """
        # Check learned corrections first
        correction = self._check_corrections(user_request)
        if correction:
            user_request = correction

        # Create plan
        plan = await self.planner.create_plan(user_request)
        plan.status = "running"

        # Store in history
        self.task_history.append({
            "request": user_request,
            "task_id": plan.task_id,
            "timestamp": datetime.now().isoformat(),
        })
        self._save_learned_data()

        return plan

    def _check_corrections(self, request: str) -> Optional[str]:
        """Check if user has previously corrected similar requests."""
        req_lower = request.lower().strip()
        for pattern, correction in self.learned_corrections.items():
            if pattern in req_lower:
                logger.info(f"Learned correction applied: '{pattern}' → '{correction}'")
                return correction
        return None

    def learn_correction(self, original_request: str, corrected_request: str):
        """
        Learn from user correction.
        Future similar requests will use the corrected version.
        """
        # Store a key phrase from original → correction
        key_phrase = original_request.lower().strip()[:50]
        self.learned_corrections[key_phrase] = corrected_request
        self._save_learned_data()
        logger.info(f"Learned: '{key_phrase}' → '{corrected_request}'")

    def get_task_stats(self) -> Dict[str, Any]:
        """Get agent statistics."""
        return {
            "total_tasks": len(self.task_history),
            "learned_corrections": len(self.learned_corrections),
            "recent_tasks": self.task_history[-5:],
            "max_steps": self.config.AGENT_MAX_STEPS,
            "auto_correct": self.config.AGENT_AUTO_CORRECT,
            "learn_preferences": self.config.AGENT_LEARN_PREFERENCES,
        }


# ═══════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════

_agent_instance: Optional[AgentCore] = None


def get_agent_core(config) -> AgentCore:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = AgentCore(config)
    return _agent_instance
