"""
agent_core.py — JARVIS v4.0
Central orchestrator: manages LLM, Skills, Memory, TTS/STT.
Added: Personality evolution, fact extraction, friendly tone.
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

logger = logging.getLogger("JARVIS.AGENT")


def _force_open_app_skill(text: str) -> Optional[str]:
    """Deterministic fallback for open-app requests when LLM misses skill tag."""
    patterns = [
        r"(?:\bopen\b|\bkhol(?:o|na|do)?\b|\blaunch\b)\s+([a-zA-Z0-9 ._+-]{2,40})",
        r"([a-zA-Z0-9 ._+-]{2,40})\s+(?:open\s+kar(?:o)?|khol(?:o|na|do)?\s+|launch\s+kar(?:o)?)",
    ]
    clean = text.strip().lower()
    for pat in patterns:
        m = re.search(pat, clean, re.IGNORECASE)
        if m:
            app_name = m.group(1).strip(" .,!?")
            if app_name:
                return f"[SKILL:open_app:{app_name}]"
    return None


class JarvisAgent:
    """Central orchestrator for JARVIS."""

    def __init__(self):
        self.config = config
        self.memory = get_memory_manager(config)
        self.skills = get_skills_engine(config)

    async def process_text_input(self, text: str, use_tts: bool = True) -> Dict[str, Any]:
        """Main entry point: user text → response."""
        try:
            # Save user message
            await self.memory.add_message("user", text)

            # Extract facts from user text
            try:
                facts = await self.memory.extract_and_store_facts(text)
                if facts:
                    logger.info(f"Facts extracted: {facts}")
            except Exception:
                pass

            # Build memory context
            memory_context = self.memory.get_context()

            # Get LLM response
            result = await get_response(text, memory_context)
            llm_response = result["response"]
            skill_tag = result.get("skill")
            if not skill_tag:
                skill_tag = _force_open_app_skill(text)

            if skill_tag:
                # Execute skill
                skill_result = await self.skills.parse_and_execute(skill_tag, memory_context)

                if skill_result.get("executed"):
                    if skill_result.get("is_data_skill"):
                        # Get 2nd pass summary for DATA skills
                        summary = await get_response_with_skill_result(
                            text, skill_result["result"], memory_context
                        )
                        final_response = summary["response"]
                        # Update personality
                        await self.memory.update_personality(len(final_response), skill_result.get("skill_name", ""))
                    else:
                        final_response = llm_response
                else:
                    # Skill failed
                    error = skill_result.get("error", "Skill failed bhai")
                    final_response = f"{llm_response} (Error: {error[:60]})"
            else:
                final_response = llm_response
                # Update personality on normal response
                await self.memory.update_personality(len(final_response), "")

            # Save assistant response
            await self.memory.add_message("assistant", final_response)
            await self.memory.save_memory()

            # TTS
            tts_path = ""
            if use_tts and final_response:
                tts_path = await generate_tts(final_response[:300])

            return {
                "response": final_response,
                "tts_path": tts_path,
                "skill_used": skill_tag,
            }

        except Exception as e:
            logger.error(f"process_text_input error: {e}")
            return {
                "response": "Kuch gadbad ho gayi bhai. Dobara try karo.",
                "tts_path": "",
                "skill_used": None,
            }

    async def get_greeting(self) -> str:
        """Generate time-aware greeting."""
        greeting = await get_greeting()
        # Track last greeting
        try:
            await self.memory.update_user_fact("last_greeting", greeting)
        except Exception:
            pass
        return greeting

    async def clear_memory(self) -> str:
        """Reset conversation history."""
        success = await self.memory.clear_memory()
        return "Memory clear ho gayi bhai." if success else "Memory clear nahi ho payi bhai."


# Singleton
_agent: Optional[JarvisAgent] = None


def get_agent() -> JarvisAgent:
    global _agent
    if _agent is None:
        _agent = JarvisAgent()
    return _agent
