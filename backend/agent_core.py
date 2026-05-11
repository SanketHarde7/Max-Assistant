"""
agent_core.py — MAX v4.0
Central orchestrator: manages LLM, Skills, Memory, TTS/STT.
v4.1 fix: Gatekeeper integrated into response pipeline.
         Banned words filtered before UI + TTS.
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
    """Deterministic fallback for open-app requests when LLM misses skill tag."""
    patterns = [
        r"(?:\bopen\b|\bkhol(?:o|na|do)?\b|\blaunch\b)\s+([a-zA-Z0-9 ._+\-]{2,40})",
        r"([a-zA-Z0-9 ._+\-]{2,40})\s+(?:open\s+kar(?:o)?|khol(?:o|na|do)?|launch\s+kar(?:o)?)",
    ]
    clean = text.strip().lower()
    for pat in patterns:
        m = re.search(pat, clean, re.IGNORECASE)
        if m:
            app_name = m.group(1).strip(" .,!?")
            if app_name:
                return f"[SKILL:open_app:{app_name}]"
    return None


class MaxAgent:
    """Central orchestrator for MAX."""

    def __init__(self):
        self.config = config
        self.memory = get_memory_manager(config)
        self.skills = get_skills_engine(config)
        self.gatekeeper = get_gatekeeper()

    async def process_text_input(self, text: str, use_tts: bool = True) -> Dict[str, Any]:
        """Main entry point: user text → gatekeeper-filtered response."""
        try:
            await self.memory.add_message("user", text)

            # Fact extraction
            try:
                facts = await self.memory.extract_and_store_facts(text)
                if facts:
                    logger.info(f"Facts extracted: {facts}")
            except Exception:
                pass

            memory_context = self.memory.get_context()

            # LLM call
            result = await get_response(text, memory_context)
            llm_response = result["response"]
            skill_tag = result.get("skill")

            # Deterministic fallback if LLM missed open-app tag
            if not skill_tag:
                skill_tag = _force_open_app_skill(text)

            if skill_tag:
                skill_result = await self.skills.parse_and_execute(skill_tag, memory_context)

                if skill_result.get("executed"):
                    if skill_result.get("is_data_skill"):
                        summary = await get_response_with_skill_result(
                            text, skill_result["result"], memory_context
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

            # ── GATEKEEPER: filter banned words from final response ──
            filtered_response = self.gatekeeper.filter(final_response)

            await self.memory.add_message("assistant", filtered_response)
            await self.memory.save_memory()

            # TTS — extra aggressive filter (no emojis, no markdown)
            tts_path = ""
            if use_tts and filtered_response:
                tts_text = self.gatekeeper.filter_for_tts(filtered_response, max_chars=300)
                tts_path = await generate_tts(tts_text)

            return {
                "response": filtered_response,
                "tts_path": tts_path,
                "skill_used": skill_tag,
            }

        except Exception as e:
            logger.error(f"process_text_input error: {e}")
            return {
                "response": "Kuch gadbad ho gayi. Dobara try karo.",
                "tts_path": "",
                "skill_used": None,
            }

    async def get_greeting(self) -> str:
        """Generate time-aware greeting, filtered by gatekeeper."""
        greeting = await get_greeting()
        # Apply gatekeeper to greeting too
        greeting = self.gatekeeper.filter(greeting)
        try:
            await self.memory.update_user_fact("last_greeting", greeting)
        except Exception:
            pass
        return greeting

    async def clear_memory(self) -> str:
        success = await self.memory.clear_memory()
        return "Memory clear ho gayi." if success else "Memory clear nahi ho payi."


# Singleton
_agent: Optional[MaxAgent] = None


def get_agent() -> MaxAgent:
    global _agent
    if _agent is None:
        _agent = MaxAgent()
    return _agent
