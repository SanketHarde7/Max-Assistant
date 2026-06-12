# Path: backend/agent_core.py
# Use: Core execution manager for custom plugins and agents.
# agent_core.py — MAX v4.5 (Ghost Mode + Full Trackers - Uncompacted)

import asyncio
import logging
import re
from typing import Dict, Any, List, Optional
from config import config
from modules.llm import get_response, get_response_with_skill_result, get_greeting, get_acknowledgment
from modules.skills import get_skills_engine
from modules.memory import get_memory_manager
from modules.tts import generate_tts
from modules.gatekeeper import get_gatekeeper
from modules.Intent_engine import get_intent_engine
from modules.listening_manager import ListeningManager
from modules.agent_loop import get_agent_loop, is_complex_goal

logger = logging.getLogger("MAX.AGENT")

# Global WebSocket reference set by main.py at startup
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
    Only runs when IntentEngine classifies as COMMAND.
    """
    text_lower = text.strip().lower()
    patterns = [
        r"(?:\bopen\b|\bkhol(?:o|na|do|de)?\b|\blaunch\b|\bstart\b)\s+([a-zA-Z0-9 ._+\-'\"]{2,40})",
        r"([a-zA-Z0-9 ._+\-'\"]{2,40})\s+(?:\bopen\s+kar(?:o|de)?|\bkhol(?:o|na|do|de)?|\blaunch\s+kar(?:o|de)?)",
        r"(?:open|khol|launch)\s+(?:the\s+)?(?:app\s+)?([a-zA-Z0-9 ._+\-'\"]{2,40})",
    ]
    for pat in patterns:
        m = re.search(pat, text_lower, re.IGNORECASE)
        if m:
            app_name = m.group(1).strip(" .,!?\"'").strip()
            if app_name and len(app_name) > 1:
                non_apps = {"it", "this", "that", "them", "me", "us", "him", "her", "something", "anything", "everything", "nothing"}
                if app_name.lower() not in non_apps:
                    return f"[SKILL:open_app:{app_name}]"
    return None


class MaxAgent:

    def __init__(self):
        self.config = config
        self.memory = get_memory_manager(config)
        self.skills = get_skills_engine(config)
        self.gatekeeper = get_gatekeeper()
        self.intent_engine = get_intent_engine(config)
        self.listening_manager = ListeningManager()
        
        # 👻 GHOST MODE INITIALIZED CORRECTLY (NOT COMMENTED OUT)
        self.ghost_mode = False
        
        # Real-time reminder scheduler
        try:
            from modules.reminder_scheduler import get_scheduler
            get_scheduler(config).start()
            logger.info("Reminder scheduler started")
        except Exception as e:
            logger.debug(f"Reminder scheduler not available: {e}")

    async def _send_ack_via_websocket(self, ack_text: str, use_tts: bool):
        global _active_websocket, _main_event_loop
        if not ack_text or not ack_text.strip():
            return
        try:
            ws = _active_websocket
            loop = _main_event_loop
            if not ws or not loop:
                return  
            
            try:
                await ws.send_json({"event": "response_text", "text": ack_text, "skill_used": None})
            except Exception as e:
                logger.debug(f"Ack text send failed: {e}")
                return  
        except Exception as e:
            logger.debug(f"Ack dispatch failed: {e}")

    async def _send_event_via_websocket(self, payload: dict):
        """Push an additive event (plan_update etc.) to the client. Never raises."""
        global _active_websocket
        ws = _active_websocket
        if not ws:
            return
        try:
            await ws.send_json(payload)
        except Exception as e:
            logger.debug(f"Event send failed: {e}")

    async def process_text_input(self, text: str, use_tts: bool = True, input_source: str = "unknown") -> Dict[str, Any]:
        print(f"\n🟢 [TRACKER: 1] Pipeline started! Input: '{text}' | Source: {input_source}")
        
        if not text or not text.strip():
            print("🔴 [TRACKER: END] Text is empty.")
            return {"response": "", "tts_path": "", "skill_used": None, "intent": "empty"}
        
        try:
            # 🚨 1. GHOST MODE INTERACTION BYPASS
            print("🟢 [TRACKER: 2] Checking Ghost Mode...")
            ghost_result = await self.process_ghost_mode_test(text)
            if ghost_result is not None:
                print(f"🟢 [TRACKER: 3] Ghost Mode Triggered! Result: {ghost_result}")
                if use_tts:
                    tts_path = await generate_tts(ghost_result["response"])
                    ghost_result["tts_path"] = tts_path
                else:
                    ghost_result["tts_path"] = ""
                ghost_result["intent"] = "ghost_mode"
                return ghost_result

            # Step 1: Listening Manager (ONLY FOR VOICE)
            print(f"🟢 [TRACKER: 4] Source is {input_source}. Checking ListeningManager...")
            if input_source == "voice":
                lm_result = self.listening_manager.process_transcript(text)
                action = lm_result.get("action")
                
                if action == "ignore":
                    print("🔴 [SILENT KILLER] ListeningManager dropped it (Missing wake word / background noise).")
                    return {"response": "", "tts_path": "", "skill_used": None, "intent": "ignored"}
                    
                if action == "reserved":
                    cmd = lm_result.get("command", "")
                    if cmd in ["stop listening", "sunna band karo", "cancel", "abort", "emergency stop"]:
                        self.listening_manager.continuous_mode = False
                    elif cmd in ["start listening", "sunna shuru karo"]:
                        self.listening_manager.continuous_mode = True
                    print(f"🟢 [TRACKER] Reserved command triggered: {cmd}")
                    return {"response": f"Reserved command triggered: {cmd}", "tts_path": "", "skill_used": f"reserved:{cmd}", "intent": "reserved"}
                    
                if action == "reply":
                    resp_text = lm_result.get("response", "")
                    tts_path = ""
                    if use_tts and resp_text:
                        tts_path = await generate_tts(resp_text)
                    print(f"🟢 [TRACKER] Quick reply triggered: {resp_text}")
                    return {"response": resp_text, "tts_path": tts_path, "skill_used": None, "intent": "reply"}

                if action == "execute":
                    skill_tag = lm_result.get("skill_tag")
                    print(f"🟢 [TRACKER] Fast Brain Execute -> {skill_tag}")
                    
                    try:
                        fast_ack = await asyncio.wait_for(get_acknowledgment(text), timeout=1.0)
                        if fast_ack:
                            asyncio.create_task(self._send_ack_via_websocket(fast_ack, False))
                    except Exception:
                        pass
                        
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

                # Resolve text
                text = lm_result.get("resolved_text", text)

            print("🟢 [TRACKER: 5] Adding to memory & Fact Extraction...")
            await self.memory.add_message("user", text)
            try:
                await self.memory.extract_and_store_facts(text)
            except Exception:
                pass

            memory_context = self.memory.get_context()

            print("🟢 [TRACKER: 6] Getting KB Context...")
            kb_prefix = ""
            try:
                from modules.knowledge_base import get_knowledge_base
                kb_ctx = await asyncio.to_thread(get_knowledge_base(self.config).query, text, top_k=3, min_similarity=0.30)
                if kb_ctx:
                    kb_prefix = kb_ctx + "\n\n"
            except Exception:
                pass
            combined_context = kb_prefix + memory_context

            print("🟢 [TRACKER: 7] Checking Intent...")
            intent = await self.intent_engine.classify(text)
            allow_skills = intent.should_execute_skill

            # 🤖 AGENT LOOP — multi-step goals get planned & executed autonomously
            if allow_skills and is_complex_goal(text):
                print("🟢 [TRACKER: 7.5] Complex goal detected → Agent Loop engaged.")
                try:
                    try:
                        ack = await asyncio.wait_for(get_acknowledgment(text), timeout=1.0)
                        if ack:
                            asyncio.create_task(self._send_ack_via_websocket(ack, use_tts))
                    except Exception:
                        pass

                    loop_result = await get_agent_loop(self.config, self.skills).run(
                        text, combined_context, self._send_event_via_websocket
                    )
                    final_response = self.gatekeeper.filter(loop_result["response"])
                    await self.memory.add_message("assistant", final_response)
                    await self.memory.save_memory()

                    tts_path = ""
                    if use_tts and final_response:
                        try:
                            tts_text = self.gatekeeper.filter_for_tts(final_response)
                            tts_path = await asyncio.wait_for(generate_tts(tts_text), timeout=15.0)
                        except Exception as e:
                            print(f"🔴 [TRACKER: ERROR] TTS Crashed: {e}")

                    print("🟢 [TRACKER: 7.9] Agent Loop complete. Returning to main.")
                    return {
                        "response": final_response,
                        "tts_path": tts_path,
                        "skill_used": loop_result.get("skills_used"),
                        "intent": "agent_loop",
                    }
                except Exception as e:
                    logger.error(f"Agent loop failed — falling back to single-shot: {e}", exc_info=True)
                    print(f"🔴 [TRACKER: 7.5 ERROR] Agent Loop failed ({e}). Using normal path.")

            print("🟢 [TRACKER: 8] Acknowledgment & LLM Call...")
            ack_task = None
            if allow_skills:  
                try:
                    ack = await asyncio.wait_for(get_acknowledgment(text), timeout=3.0)
                    if ack:
                        ack_task = asyncio.create_task(self._send_ack_via_websocket(ack, use_tts))
                except Exception:
                    pass

            result = await get_response(text, combined_context, allow_skills=allow_skills)
            llm_response = result["response"]
            skill_tag = result.get("skill") if allow_skills else None
            print(f"🟢 [TRACKER: 9] LLM Replied. Skill: {skill_tag}")

            if allow_skills and not skill_tag:
                skill_tag = _force_open_app_skill(text)

            final_response = llm_response
            if skill_tag:
                print(f"🟢 [TRACKER: 10] Executing Skill: {skill_tag}")
                skill_result = await self.skills.parse_and_execute(skill_tag, combined_context, text)
                if skill_result.get("executed"):
                    skill_output = skill_result.get("result", "").strip()
                    
                    skill_failed = False
                    fail_indicators = ["could not find", "failed", "error", "not found", "not installed", "needed:", "missing", "unable to", "cannot", "does not exist", "no such"]
                    if skill_output:
                        lower_output = skill_output.lower()
                        skill_failed = any(ind in lower_output for ind in fail_indicators)
                    
                    if skill_result.get("is_data_skill"):
                        summary = await get_response_with_skill_result(text, skill_output, combined_context)
                        final_response = summary["response"]
                        await self.memory.update_personality(len(final_response), skill_result.get("skill_name", ""))
                    elif skill_failed:
                        final_response = skill_output
                    else:
                        final_response = skill_output or llm_response
                else:
                    error = skill_result.get("error", "Skill failed")
                    final_response = f"{llm_response} (Error: {error[:60]})"
            else:
                await self.memory.update_personality(len(final_response), "")

            filtered = self.gatekeeper.filter(final_response)
            print("🟢 [TRACKER: 11] Filtering done. Text ready for TTS.")

            try:
                from modules.skill_forge import get_skill_forge
                get_skill_forge(self.config).record_gap(text, filtered)
            except Exception:
                pass

            await self.memory.add_message("assistant", filtered)
            await self.memory.save_memory()

            tts_path = ""
            if use_tts and filtered:
                print("🟢 [TRACKER: 12] Generating Audio from Kokoro...")
                try:
                    tts_text = self.gatekeeper.filter_for_tts(filtered)
                    tts_path = await asyncio.wait_for(generate_tts(tts_text), timeout=15.0)
                    print(f"🟢 [TRACKER: 13] Audio Generated! Path: {tts_path}")
                except Exception as e:
                    print(f"🔴 [TRACKER: ERROR] TTS Crashed: {e}")

            if ack_task and not ack_task.done():
                try:
                    await asyncio.wait_for(ack_task, timeout=2.0)
                except Exception:
                    pass

            print("🟢 [TRACKER: 14] Pipeline Complete. Returning to main.")
            return {
                "response": filtered,
                "tts_path": tts_path,
                "skill_used": skill_tag,
                "intent": intent.type.value,
            }

        except Exception as e:
            print(f"🔴 [FATAL ERROR] process_text_input crashed: {e}")
            logger.error(f"process_text_input error: {e}", exc_info=True)
            return {
                "response": "Something went wrong. Try again?",
                "tts_path": "",
                "skill_used": None,
                "intent": "error"
            }

    async def get_greeting(self) -> str:
        greeting = self.gatekeeper.filter(await get_greeting())
        try:
            await self.memory.update_user_fact("last_greeting", greeting)
        except Exception:
            pass
        return greeting

    async def clear_memory(self) -> str:
        try:
            success = await self.memory.clear_memory()
            return "Memory cleared." if success else "Could not clear memory."
        except Exception as e:
            logger.error(f"Memory clear failed: {e}")
            return f"Error clearing memory: {str(e)}"
    
    async def process_ghost_mode_test(self, user_text: str) -> Optional[dict]:
        import pyautogui
        import re
        from modules.listening_manager import LocalFastBrain
        pyautogui.FAILSAFE = False 
        
        # 🛠️ FIX 1: Punctuation (.,!?) hatao taaki STT ke full-stops se match fail na ho
        text_clean = re.sub(r'[^\w\s]', '', user_text.lower()).strip()

        # 1. Activation Check
        activation_phrases = ["activate ghost mode", "ghost mode on", "start ghost mode", "enable ghost mode"]
        if any(phrase in text_clean for phrase in activation_phrases):
            self.ghost_mode = True
            logger.info("👻 Ghost Mode Activated via Test Protocol")
            return {"response": "Ghost mode active.", "skill_used": "ghost_activate"}

        if not self.ghost_mode:
            return None

        # 2. Deactivation Check
        deactivation_phrases = ["exit ghost mode", "terminate protocol", "ghost mode off", "stop ghost mode", "disable ghost mode", "deactivate ghost mode"]
        if any(phrase in text_clean for phrase in deactivation_phrases):
            self.ghost_mode = False
            logger.info("🚫 Ghost Mode Deactivated")
            return {"response": "Exited.", "skill_used": "ghost_deactivate"}

        # 3. Deterministic Command Mapping
        try:
            # 🛠️ FIX 2: Exact match (==) ki jagah Substring match (in) use kiya
            if any(cmd in text_clean for cmd in ["press enter", "enter maro", "hit enter", "enter daba"]):
                pyautogui.press('enter')
                return {"response": "Done.", "skill_used": "key_enter"}
                
            elif any(cmd in text_clean for cmd in ["press tab", "tab maro", "tab daba"]):
                pyautogui.press('tab')
                return {"response": "Done.", "skill_used": "key_tab"}
                
            elif any(cmd in text_clean for cmd in ["press backspace", "backspace", "clear", "undo"]):
                pyautogui.press('backspace')
                return {"response": "Done.", "skill_used": "key_backspace"}

            elif any(cmd in text_clean for cmd in ["switch window", "window badlo", "alt tab"]):
                pyautogui.hotkey('alt', 'tab')
                return {"response": "Done.", "skill_used": "hotkey_alt_tab"}
                
            elif any(cmd in text_clean for cmd in ["minimize app", "minimize window", "minimize"]):
                pyautogui.hotkey('win', 'down')
                return {"response": "Done.", "skill_used": "hotkey_minimize"}

            elif any(cmd in text_clean for cmd in ["volume up", "aawaz badhao", "increase volume"]):
                pyautogui.press('volumeup')
                return {"response": "Done.", "skill_used": "volume_up"}
                
            elif any(cmd in text_clean for cmd in ["volume down", "aawaz kam karo", "decrease volume"]):
                pyautogui.press('volumedown')
                return {"response": "Done.", "skill_used": "volume_down"}

            # 4. Fallback: Type the text directly
            # Yahan hum original user_text use karenge taaki capital letters aur dots type karte waqt sahi rahein
            # We must strip the wake word (like "max") before typing it!
            final_type_text = LocalFastBrain.strip_wake_word(user_text)
            if final_type_text:
                pyautogui.write(final_type_text + " ", interval=0.01)
            # Returning empty response prevents MAX from saying "Typed." every single time!
            return {"response": "", "skill_used": "direct_dictation"}

        except Exception as e:
            logger.error(f"Ghost Mode hardware execution error: {e}")
            return {"response": "Error.", "skill_used": "ghost_error"}

# Singleton
_agent: Optional[MaxAgent] = None

def get_agent() -> MaxAgent:
    global _agent
    if _agent is None:
        _agent = MaxAgent()
    return _agent