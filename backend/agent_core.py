"""
agent_core.py — MAX v4.2
Pipeline:
  user text → fact extract → KB query → LLM → skill exec → gatekeeper → TTS
"""
import asyncio
import logging
import re
from typing import Dict, Any, Optional
from config import config
from modules.llm import get_response, get_response_with_skill_result, get_greeting
from modules.skills import get_skills_engine
from modules.memory import get_memory_manager
from modules.tts import generate_tts
from modules.gatekeeper import get_gatekeeper

logger = logging.getLogger("MAX.AGENT")


def _force_open_app_skill(text: str) -> Optional[str]:
    """Deterministic fallback for missed open-app skill tags."""
    patterns = [
        r"(?:\bopen\b|\bkhol(?:o|na|do)?\b|\blaunch\b)\s+([a-zA-Z0-9 ._+\-]{2,40})",
        r"([a-zA-Z0-9 ._+\-]{2,40})\s+(?:open\s+kar(?:o)?|khol(?:o|na|do)?|launch\s+kar(?:o)?)",
    ]
    for pat in patterns:
        m = re.search(pat, text.strip().lower(), re.IGNORECASE)
        if m:
            app_name = m.group(1).strip(" .,!?")
            if app_name and len(app_name) > 1:
                return f"[SKILL:open_app:{app_name}]"
    return None


class MaxAgent:

    def __init__(self):
        self.config     = config
        self.memory     = get_memory_manager(config)
        self.skills     = get_skills_engine(config)
        self.gatekeeper = get_gatekeeper()

    async def process_text_input(self, text: str, use_tts: bool = True) -> Dict[str, Any]:
        try:
            await self.memory.add_message("user", text)

            # Silent fact extraction
            try:
                await self.memory.extract_and_store_facts(text)
            except Exception:
                pass

            memory_context = self.memory.get_context()

            # ── Knowledge Base injection ──────────────────
            kb_prefix = ""
            try:
                from modules.knowledge_base import get_knowledge_base
                kb_ctx = get_knowledge_base(self.config).query(text, top_k=3, min_similarity=0.30)
                if kb_ctx:
                    kb_prefix = kb_ctx + "\n\n"
                    logger.info("KB context injected into prompt")
            except Exception as e:
                logger.debug(f"KB query skipped: {e}")

            combined_context = kb_prefix + memory_context

            # ── LLM call ──────────────────────────────────
            result       = await get_response(text, combined_context)
            llm_response = result["response"]
            skill_tag    = result.get("skill") or _force_open_app_skill(text)

            # ── Skill execution ───────────────────────────
            if skill_tag:
                skill_result = await self.skills.parse_and_execute(skill_tag, combined_context)
                if skill_result.get("executed"):
                    if skill_result.get("is_data_skill"):
                        summary = await get_response_with_skill_result(
                            text, skill_result["result"], combined_context
                        )
                        final_response = summary["response"]
                        await self.memory.update_personality(
                            len(final_response), skill_result.get("skill_name", "")
                        )
                    else:
                        final_response = llm_response
                else:
                    error = skill_result.get("error", "Skill failed")
                    final_response = f"{llm_response} (Error: {error[:60]})"
            else:
                final_response = llm_response
                await self.memory.update_personality(len(final_response), "")

            # ── Gatekeeper ────────────────────────────────
            filtered = self.gatekeeper.filter(final_response)

            await self.memory.add_message("assistant", filtered)
            await self.memory.save_memory()

            # ── TTS ───────────────────────────────────────
            tts_path = ""
            if use_tts and filtered:
                tts_text = self.gatekeeper.filter_for_tts(filtered, max_chars=300)
                tts_path = await generate_tts(tts_text)

            return {"response": filtered, "tts_path": tts_path, "skill_used": skill_tag}

        except Exception as e:
            logger.error(f"process_text_input error: {e}", exc_info=True)
            return {"response": "Something went wrong. Try again.", "tts_path": "", "skill_used": None}

    async def get_greeting(self) -> str:
        greeting = self.gatekeeper.filter(await get_greeting())
        try:
            await self.memory.update_user_fact("last_greeting", greeting)
        except Exception:
            pass
        return greeting

    async def clear_memory(self) -> str:
        return "Memory cleared." if await self.memory.clear_memory() else "Could not clear memory."


_agent: Optional[MaxAgent] = None


def get_agent() -> MaxAgent:
    global _agent
    if _agent is None:
        _agent = MaxAgent()
    return _agent
