"""
agent_core.py — MAX v4.2
Pipeline:
  user text → IntentEngine.classify() → fact extract → KB query
           → LLM (allow_skills based on intent) → skill exec → gatekeeper → TTS

KEY CHANGE v4.2:
  IntentEngine runs BEFORE LLM call.
  - Prevents false skill triggers (e.g., "Can you play YouTube?" no longer plays YouTube)
  - allow_skills=False forces the LLM into conversational-only mode
  - allow_skills=True = normal behavior, LLM can emit skill tags
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
from modules.language_detector import is_hindi_by_regex
from modules.gatekeeper import get_gatekeeper
from modules.Intent_engine import get_intent_engine
from modules.listening_manager import ListeningManager

logger = logging.getLogger("MAX.AGENT")


def _force_open_app_skill(text: str) -> Optional[str]:
    """
    Deterministic fallback for missed open-app skill tags.
    Only runs when IntentEngine classifies as COMMAND (allow_skills=True).
    """
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
        self.intent_engine = get_intent_engine(config)
        self.listening_manager = ListeningManager()
     # ── Real-time reminder scheduler ──────────────────────
        from modules.reminder_scheduler import get_scheduler
        get_scheduler(config).start()
        # Daemon thread — auto-stops when process exits.
     
    async def process_text_input(self, text: str, use_tts: bool = True, input_source: str = "unknown") -> Dict[str, Any]:
        try:
            # ── MAX-AILE Listening Manager Intercept ──
            lm_result = self.listening_manager.process_transcript(text)
            action = lm_result.get("action")
            
            if action == "ignore":
                logger.info("ListeningManager: Background noise/unrelated, ignoring.")
                return {"response": "", "tts_path": "", "skill_used": None, "intent": "ignored"}
                
            if action == "reserved":
                cmd = lm_result.get("command")
                # Sync backend continuous_mode with frontend state
                if cmd in ["stop listening", "sunna band karo", "cancel", "abort", "emergency stop"]:
                    self.listening_manager.continuous_mode = False
                elif cmd in ["start listening", "sunna shuru karo"]:
                    self.listening_manager.continuous_mode = True
                return {"response": f"Reserved command triggered: {cmd}", "tts_path": "", "skill_used": f"reserved:{cmd}", "intent": "reserved"}
                
            if action == "reply":
                resp_text = lm_result.get("response", "")
                logger.info(f"ListeningManager Reply: {resp_text}")
                tts_path = ""
                if use_tts and resp_text:
                    tts_path = await generate_tts(resp_text)
                return {"response": resp_text, "tts_path": tts_path, "skill_used": None, "intent": "reply"}

            resolved_text = lm_result.get("resolved_text", text)

            if action == "execute":
                skill_tag = lm_result.get("skill_tag")
                tier = lm_result.get("tier")
                logger.info(f"ListeningManager: Fast Brain Tier {tier} Execute -> {skill_tag}")
                memory_context = self.memory.get_context()
                skill_result = await self.skills.parse_and_execute(skill_tag, memory_context, resolved_text)
                if skill_result.get("executed"):
                    final_response = skill_result.get("result", "").strip() or "Done."
                else:
                    error = skill_result.get("error", "Skill failed")
                    final_response = f"Could not execute. Error: {error}"
                tts_path = ""
                if use_tts and final_response:
                    tts_path = await generate_tts(self.gatekeeper.filter_for_tts(final_response, max_chars=300))
                return {"response": final_response, "tts_path": tts_path, "skill_used": skill_tag, "intent": "fast_brain"}

            text = resolved_text

            await self.memory.add_message("user", text)

            # ── Silent fact extraction ──────────────────
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

            # ── Intent Classification (RUNS FIRST) ───────
            # This decides whether the LLM is allowed to emit skill tags.
            # Prevents: "Can you play YouTube?" from triggering youtube_play skill.
            intent = await self.intent_engine.classify(text)
            allow_skills = intent.should_execute_skill
            logger.info(f"Intent: {intent.type.value} | allow_skills={allow_skills} | reason='{intent.reason}'")

            # ── LLM call ──────────────────────────────────
            result       = await get_response(text, combined_context, allow_skills=allow_skills)
            llm_response = result["response"]

            # Skill tag from LLM (only respected if allow_skills=True)
            # If allow_skills=False, get_response already strips skill tags
            skill_tag = result.get("skill") if allow_skills else None

            # Deterministic fallback for open_app only runs on COMMAND intents
            if allow_skills and not skill_tag:
                skill_tag = _force_open_app_skill(text)

            # ── Skill execution ───────────────────────────
            if skill_tag:
                skill_result = await self.skills.parse_and_execute(skill_tag, combined_context, text)
                if skill_result.get("executed"):
                    skill_output = skill_result.get("result", "").strip()
                    
                    # Check if skill actually failed (contains error indicators)
                    skill_failed = False
                    fail_indicators = ["could not find", "failed", "error", "not found", "not installed", "needed:", "missing"]
                    if skill_output:
                        lower_output = skill_output.lower()
                        skill_failed = any(ind in lower_output for ind in fail_indicators)
                    
                    if skill_result.get("is_data_skill"):
                        summary = await get_response_with_skill_result(
                            text, skill_output, combined_context
                        )
                        final_response = summary["response"]
                        await self.memory.update_personality(
                            len(final_response), skill_result.get("skill_name", "")
                        )
                    elif skill_failed:
                        # Skill ran but reported failure — use the ACTUAL skill error, not the LLM's hopeful text
                        final_response = skill_output
                        logger.warning(f"Skill reported failure: {skill_output[:100]}")
                    else:
                        # Skill succeeded — use skill result text
                        final_response = skill_output or llm_response
                else:
                    error = skill_result.get("error", "Skill failed")
                    final_response = f"{llm_response} (Error: {error[:60]})"

            else:
                final_response = llm_response
                await self.memory.update_personality(len(final_response), "")

            # ── Gatekeeper ────────────────────────────────
            filtered = self.gatekeeper.filter(final_response)

            # ── SkillForge soft gap trigger ───────────────
            try:
                from modules.skill_forge import get_skill_forge
                get_skill_forge(self.config).record_gap(text, filtered)
            except Exception as e:
                logger.debug(f"Failed to record gap in SkillForge: {e}")

            await self.memory.add_message("assistant", filtered)
            await self.memory.save_memory()

            # ── TTS ───────────────────────────────────────
            tts_path = ""
            if use_tts and filtered:
                tts_text = self.gatekeeper.filter_for_tts(filtered, max_chars=300)
                voice_override = ""
                source = (input_source or "").lower()
                if source == "text":
                    try:
                        if is_hindi_by_regex(text):
                            voice_override = self.config.TTS_VOICE_HINDI
                    except Exception as e:
                        logger.debug(f"Regex Hindi detect failed: {e}")
                tts_path = await generate_tts(tts_text, voice=voice_override)

            return {
                "response": filtered,
                "tts_path": tts_path,
                "skill_used": skill_tag,
                "intent": intent.type.value,   # Useful for debugging/UI
            }

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