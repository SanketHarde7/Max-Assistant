# Path: backend/agent_core.py
# Use: Core execution manager for custom plugins and agents.
# agent_core.py — MAX v4.3
# Pipeline:
#   user text → IntentEngine.classify() → fact extract → KB query
#            → LLM (allow_skills based on intent) → skill exec → gatekeeper → TTS
#
# KEY CHANGES v4.3:
#   - Fixed circular import risk (removed runtime import of main module)
#   - Better ack system with non-blocking send and silent fail
#   - Improved error handling with graceful degradation
#   - Added structured logging for debugging
import asyncio
import logging
import re
from typing import Dict, Any, Optional
from config import config
from modules.llm import get_response, get_response_with_skill_result, get_greeting, get_acknowledgment
from modules.skills import get_skills_engine
from modules.memory import get_memory_manager
from modules.tts import generate_tts
from modules.gatekeeper import get_gatekeeper
from modules.Intent_engine import get_intent_engine
from modules.listening_manager import ListeningManager

logger = logging.getLogger("MAX.AGENT")

# Global WebSocket reference set by main.py at startup
# This avoids circular imports while allowing agent_core to send messages
_active_websocket = None
_main_event_loop = None

def set_websocket_globals(websocket, loop):
    """Called by main.py on WebSocket connection to set globals."""
    global _active_websocket, _main_event_loop
    _active_websocket = websocket
    _main_event_loop = loop


def _force_open_app_skill(text: str) -> Optional[str]:
    """
    Deterministic fallback for missed open-app skill tags.
    Handles multiple apps separated by 'and', 'aur', or commas.
    Returns multiple [SKILL:...] tags when needed.
    Only runs when IntentEngine classifies as COMMAND (allow_skills=True).
    """
    text_lower = text.strip().lower()

    # Known websites that should use web_open instead of open_app
    _WEB_MAP = {
        "youtube": "youtube.com", "gmail": "gmail.com", "github": "github.com",
        "google": "google.com", "chatgpt": "chatgpt.com", "chat gpt": "chatgpt.com",
        "gemini": "gemini.google.com", "twitter": "twitter.com", "x": "x.com",
        "instagram": "instagram.com", "linkedin": "linkedin.com", "reddit": "reddit.com",
        "netflix": "netflix.com", "notion": "notion.so", "figma": "figma.com",
        "stackoverflow": "stackoverflow.com", "stack overflow": "stackoverflow.com",
        "whatsapp web": "web.whatsapp.com", "facebook": "facebook.com",
    }

    # Words that are not real apps
    _NON_APPS = {
        "it", "this", "that", "them", "me", "us", "him", "her",
        "something", "anything", "everything", "nothing",
        "please", "now", "quickly", "fast", "both",
    }

    # Extract the full app-list string after trigger verbs.
    # Use a NON-GREEDY match up to end-of-line filler words.
    trigger_pattern = re.compile(
        r"(?:\bopen\b|\bkhol(?:o|na|do|de)?\b|\blaunch\b|\bstart\b)"
        r"\s+(?:the\s+)?(?:app(?:s)?\s+)?"
        r"(.+?)(?:\s+(?:karo?|kardo|de|please|abhi|now)\s*$|$)",
        re.IGNORECASE,
    )
    # Also handle suffix pattern: "X aur Y open karo"
    suffix_pattern = re.compile(
        r"^(.+?)\s+(?:\bopen\s+kar(?:o|de)?|\bkhol(?:o|na|do|de)?|\blaunch\s+kar(?:o|de)?)",
        re.IGNORECASE,
    )

    apps_str = None
    for pat in (trigger_pattern, suffix_pattern):
        m = pat.search(text_lower)
        if m:
            apps_str = m.group(1).strip()
            break

    if not apps_str:
        return None

    # Split by "and", "aur", "," — these are list separators, not app names
    raw_parts = re.split(r"\s+(?:and|aur)\s+|,\s*", apps_str)

    tags = []
    for part in raw_parts:
        app_name = part.strip(" .,!?\"'").strip()
        if not app_name or len(app_name) <= 1:
            continue
        if app_name.lower() in _NON_APPS:
            continue

        # Route to web_open for known websites
        web_url = _WEB_MAP.get(app_name.lower())
        if web_url:
            tags.append(f"[SKILL:web_open:{web_url}]")
        else:
            tags.append(f"[SKILL:open_app:{app_name}]")

    if not tags:
        return None
    return " ".join(tags)


class MaxAgent:

    def __init__(self):
        self.config = config
        self.memory = get_memory_manager(config)
        self.skills = get_skills_engine(config)
        self.gatekeeper = get_gatekeeper()
        self.intent_engine = get_intent_engine(config)
        self.listening_manager = ListeningManager()
        
        # Real-time reminder scheduler
        try:
            from modules.reminder_scheduler import get_scheduler
            get_scheduler(config).start()
            logger.info("Reminder scheduler started")
        except Exception as e:
            logger.debug(f"Reminder scheduler not available: {e}")

    async def _send_ack_via_websocket(self, ack_text: str, use_tts: bool):
        """
        Send acknowledgment via WebSocket if available.
        Completely non-blocking - silently fails if WebSocket unavailable.
        """
        global _active_websocket, _main_event_loop
        
        if not ack_text or not ack_text.strip():
            return
            
        try:
            ws = _active_websocket
            loop = _main_event_loop
            
            if not ws or not loop:
                return  # No WebSocket, skip silently
            
            # Send text via WebSocket
            try:
                await ws.send_json({
                    "event": "response_text",
                    "text": ack_text,
                    "skill_used": None,
                })
            except Exception as e:
                logger.debug(f"Ack text send failed: {e}")
                return  # Don't try TTS if text send failed
            
            # Send TTS
            if use_tts:
                try:
                    ack_tts_path = await asyncio.wait_for(generate_tts(ack_text), timeout=5.0)
                    if ack_tts_path:
                        import base64
                        import os
                        try:
                            if os.path.exists(ack_tts_path):
                                with open(ack_tts_path, "rb") as f:
                                    encoded_audio = base64.b64encode(f.read()).decode('utf-8')
                                    await ws.send_json({
                                        "event": "audio_response",
                                        "audio": encoded_audio,
                                    })
                                # Clean up temp file
                                try:
                                    os.remove(ack_tts_path)
                                except Exception:
                                    pass
                        except Exception as e:
                            logger.debug(f"Ack TTS send failed: {e}")
                except asyncio.TimeoutError:
                    logger.debug("Ack TTS generation timed out")
                except Exception as e:
                    logger.debug(f"Ack TTS failed: {e}")
                    
        except Exception as e:
            logger.debug(f"Ack dispatch completely failed: {e}")

    async def process_text_input(self, text: str, use_tts: bool = True, input_source: str = "unknown") -> Dict[str, Any]:
        """
        Main processing pipeline for user text input.
        Returns dict with response, tts_path, skill_used, and intent.
        """
        if not text or not text.strip():
            return {"response": "", "tts_path": "", "skill_used": None, "intent": "empty"}
        
        try:
            # Step 1: Listening Manager Intercept
            lm_result = self.listening_manager.process_transcript(text)
            action = lm_result.get("action")
            
            if action == "ignore":
                logger.info("ListeningManager: Background noise/unrelated, ignoring.")
                return {"response": "", "tts_path": "", "skill_used": None, "intent": "ignored"}
                
            if action == "reserved":
                cmd = lm_result.get("command", "")
                if cmd in ["stop listening", "sunna band karo", "cancel", "abort", "emergency stop"]:
                    self.listening_manager.continuous_mode = False
                elif cmd in ["start listening", "sunna shuru karo"]:
                    self.listening_manager.continuous_mode = True
                return {
                    "response": f"Reserved command triggered: {cmd}",
                    "tts_path": "",
                    "skill_used": f"reserved:{cmd}",
                    "intent": "reserved"
                }
                
            if action == "reply":
                resp_text = lm_result.get("response", "")
                tts_path = ""
                if use_tts and resp_text:
                    tts_path = await generate_tts(resp_text)
                return {"response": resp_text, "tts_path": tts_path, "skill_used": None, "intent": "reply"}

            if action == "execute":
                skill_tag = lm_result.get("skill_tag")
                tier = lm_result.get("tier")
                logger.info(f"ListeningManager: Fast Brain Tier {tier} Execute -> {skill_tag}")
                memory_context = self.memory.get_context()
                skill_result = await self.skills.parse_and_execute(skill_tag, memory_context, text)
                if skill_result.get("executed"):
                    final_response = skill_result.get("result", "").strip() or "Done."
                else:
                    error = skill_result.get("error", "Skill failed")
                    final_response = f"Could not execute. Error: {error}"
                tts_path = ""
                if use_tts and final_response:
                    tts_path = await generate_tts(self.gatekeeper.filter_for_tts(final_response))
                return {"response": final_response, "tts_path": tts_path, "skill_used": skill_tag, "intent": "fast_brain"}

            # Resolve text (may have been modified by listening manager)
            text = lm_result.get("resolved_text", text)

            # Step 2: Add to memory
            await self.memory.add_message("user", text)

            # Step 3: Silent fact extraction
            try:
                await self.memory.extract_and_store_facts(text)
            except Exception:
                pass

            # Step 4: Get memory context
            memory_context = self.memory.get_context()

            # Step 5: Knowledge Base injection
            kb_prefix = ""
            try:
                from modules.knowledge_base import get_knowledge_base
                kb_ctx = await asyncio.to_thread(
                    get_knowledge_base(self.config).query, text, top_k=3, min_similarity=0.30
                )
                if kb_ctx:
                    kb_prefix = kb_ctx + "\n\n"
                    logger.info("KB context injected into prompt")
            except Exception as e:
                logger.debug(f"KB query skipped: {e}")

            combined_context = kb_prefix + memory_context

            # Step 6: Intent Classification
            intent = await self.intent_engine.classify(text)
            allow_skills = intent.should_execute_skill
            logger.info(f"Intent: {intent.type.value} | allow_skills={allow_skills} | reason='{intent.reason}'")

            # Step 7: Fast Pre-call Acknowledgment (fire and forget)
            ack_task = None
            if allow_skills:  # Only ack for action commands, not casual chat
                try:
                    ack = await asyncio.wait_for(get_acknowledgment(text), timeout=3.0)
                    if ack:
                        # Non-blocking ack send
                        ack_task = asyncio.create_task(
                            self._send_ack_via_websocket(ack, use_tts)
                        )
                except asyncio.TimeoutError:
                    pass  # Silent fail - ack is not critical
                except Exception as e:
                    logger.debug(f"Ack generation failed: {e}")

            # Step 8: LLM call
            result = await get_response(text, combined_context, allow_skills=allow_skills)
            llm_response = result["response"]

            # Step 9: Skill tag extraction (only if skills allowed)
            skill_tag = result.get("skill") if allow_skills else None

            # Deterministic fallback for open_app
            if allow_skills and not skill_tag:
                skill_tag = _force_open_app_skill(text)

            # Step 10: Skill execution
            final_response = llm_response
            if skill_tag:
                skill_result = await self.skills.parse_and_execute(skill_tag, combined_context, text)
                if skill_result.get("executed"):
                    skill_output = skill_result.get("result", "").strip()
                    
                    # Check if skill actually failed
                    skill_failed = False
                    fail_indicators = [
                        "could not find", "failed", "error", "not found",
                        "not installed", "needed:", "missing", "unable to",
                        "cannot", "does not exist", "no such"
                    ]
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
                        # Skill reported failure — use the error directly
                        final_response = skill_output
                        logger.warning(f"Skill reported failure: {skill_output[:100]}")
                    else:
                        # Skill succeeded
                        final_response = skill_output or llm_response
                else:
                    error = skill_result.get("error", "Skill failed")
                    final_response = f"{llm_response} (Error: {error[:60]})"
            else:
                await self.memory.update_personality(len(final_response), "")

            # Step 11: Gatekeeper filtering
            filtered = self.gatekeeper.filter(final_response)

            # Step 12: SkillForge soft gap trigger
            try:
                from modules.skill_forge import get_skill_forge
                get_skill_forge(self.config).record_gap(text, filtered)
            except Exception as e:
                logger.debug(f"Failed to record gap in SkillForge: {e}")

            # Step 13: Save to memory
            await self.memory.add_message("assistant", filtered)
            await self.memory.save_memory()

            # Step 14: TTS generation
            tts_path = ""
            if use_tts and filtered:
                try:
                    tts_text = self.gatekeeper.filter_for_tts(filtered)
                    tts_path = await asyncio.wait_for(generate_tts(tts_text), timeout=15.0)
                except asyncio.TimeoutError:
                    logger.warning("TTS generation timed out")
                except Exception as e:
                    logger.error(f"TTS generation failed: {e}")

            # Wait for ack task to complete (don't let it hang)
            if ack_task and not ack_task.done():
                try:
                    await asyncio.wait_for(ack_task, timeout=2.0)
                except Exception:
                    pass

            return {
                "response": filtered,
                "tts_path": tts_path,
                "skill_used": skill_tag,
                "intent": intent.type.value,
            }

        except Exception as e:
            logger.error(f"process_text_input error: {e}", exc_info=True)
            return {
                "response": "Something went wrong. Try again?",
                "tts_path": "",
                "skill_used": None,
                "intent": "error"
            }

    async def get_greeting(self) -> str:
        """Get a dynamic greeting from the LLM."""
        greeting = self.gatekeeper.filter(await get_greeting())
        try:
            await self.memory.update_user_fact("last_greeting", greeting)
        except Exception:
            pass
        return greeting

    async def clear_memory(self) -> str:
        """Clear conversation memory."""
        try:
            success = await self.memory.clear_memory()
            return "Memory cleared." if success else "Could not clear memory."
        except Exception as e:
            logger.error(f"Memory clear failed: {e}")
            return f"Error clearing memory: {str(e)}"


# Singleton
_agent: Optional[MaxAgent] = None


def get_agent() -> MaxAgent:
    global _agent
    if _agent is None:
        _agent = MaxAgent()
    return _agent
