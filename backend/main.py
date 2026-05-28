"""
main.py — MAX v4.2
Backend: FastAPI + WebSocket + REST endpoints.
Added: /api/wake-check endpoint for wake word detection.
"""
import os
import sys
import logging
import base64
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ── Ensure project root in path ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import config
from agent_core import get_agent
from modules.stt import transcribe_audio, transcribe_file, transcribe_wake_word
from modules.tts import generate_tts
from modules.llm import get_greeting
from modules.skills import get_skills_engine
from modules.memory import get_memory_manager
from modules.email_agent import get_email_agent
from modules.calendar_agent import get_calendar_agent
from modules.browser_agent import get_browser_agent
from modules.smarthome_agent import get_smarthome_agent
from modules.plugin_loader import get_plugin_loader
from modules.knowledge_indexer import get_knowledge_indexer
from modules.knowledge_base import get_knowledge_base
import threading as _threading
import asyncio
from modules.health_buddy import HealthBuddy

# ── Global WebSocket & Health Buddy References ──
active_websocket: Optional[WebSocket] = None
main_loop: Optional[asyncio.AbstractEventLoop] = None
health_buddy_instance: Optional[HealthBuddy] = None

def send_health_buddy_alert(payload):
    global active_websocket, main_loop
    if active_websocket and main_loop:
        async def _send():
            try:
                await active_websocket.send_json(payload)
            except Exception as e:
                logger.warning(f"Failed to stream health alert: {e}")
        asyncio.run_coroutine_threadsafe(_send(), main_loop)

# ═══════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO if not config.DEBUG else logging.DEBUG,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("MAX.API")

# ═══════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════

app = FastAPI(
    title="MAX API",
    description="the user's AI Assistant Backend",
    version="4.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _on_startup():
    """
    Runs once when FastAPI server starts.
    1. Starts reminder background daemon (checks every 30s for due reminders)
    2. Auto-indexes .md files from backend/knowledge/ into ChromaDB
    """
    # 1. Reminder daemon
    try:
        from modules.reminder_agent import start_reminder_daemon
        start_reminder_daemon(config)
        logger.info("Reminder daemon started")
    except Exception as e:
        logger.warning(f"Reminder daemon failed: {e}")

    # 2. Knowledge base auto-index (runs in background thread, non-blocking)
    def _build_kb():
        try:
            from modules.knowledge_base import auto_index_on_startup
            auto_index_on_startup(config)
        except Exception as e:
            logger.warning(f"KB auto-index: {e}")

    _threading.Thread(target=_build_kb, daemon=True, name="MAX-KB-Init").start()

    # 3. Health Buddy daemon
    try:
        global health_buddy_instance
        health_buddy_instance = HealthBuddy(send_health_buddy_alert)
        health_buddy_instance.start()
        logger.info("Health Buddy started")
    except Exception as e:
        logger.warning(f"Health Buddy start failed: {e}")


@app.on_event("shutdown")
async def _on_shutdown():
    global health_buddy_instance
    if health_buddy_instance:
        health_buddy_instance.stop()
        logger.info("Health Buddy stopped")


@app.on_event("startup")
async def startup_event():
    try:
        get_knowledge_indexer(config).refresh_if_needed()
        logger.info("Knowledge index ready.")
    except Exception as e:
        logger.warning(f"Knowledge index startup failed: {e}")


# ═══════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════

class TextInput(BaseModel):
    text: str
    tts: bool = True

class VoiceRequest(BaseModel):
    audio: str

class WakeCheckRequest(BaseModel):
    audio: str

class CodeRequest(BaseModel):
    language: str = "python"
    description: str

class RunCodeRequest(BaseModel):
    filepath: str

class ReviewCodeRequest(BaseModel):
    filepath: str

class FixCodeRequest(BaseModel):
    filepath: str
    issue: str

class ProjectScaffoldRequest(BaseModel):
    project_type: str
    project_name: str

class WeatherRequest(BaseModel):
    city: str = "auto"

class VolumeRequest(BaseModel):
    action: str = "up"
    value: int = 10

class OpenAppRequest(BaseModel):
    app_name: str

class OpenUrlRequest(BaseModel):
    url: str

class WhatsAppRequest(BaseModel):
    contact: str
    message: str

class TypeTextRequest(BaseModel):
    text: str

class TimerRequest(BaseModel):
    seconds: int = 60
    label: str = "Timer"

class ShutdownRequest(BaseModel):
    delay: int = 30

class RestartRequest(BaseModel):
    delay: int = 30

class EmailSendRequest(BaseModel):
    to: str
    subject: str
    body: str

class CalendarAddRequest(BaseModel):
    title: str
    date: str
    time: str = ""

class BrowserOpenRequest(BaseModel):
    url: str

class BrowserActionRequest(BaseModel):
    selector: str
    text: str = ""

class BrowserScrapeRequest(BaseModel):
    url: str
    query: str

class FanRequest(BaseModel):
    action: str

class LightRequest(BaseModel):
    action: str

class ACRequest(BaseModel):
    action: str
    value: str = ""

class BrightnessRequest(BaseModel):
    action: str
    value: int = 10

class ClipboardRequest(BaseModel):
    action: str
    text: str = ""

# ═══════════════════════════════════════════════════
# WAKE WORD — NEW ENDPOINT
# ═══════════════════════════════════════════════════

WAKE_PHRASES = ["hey max", "hello max", "ok max", "max", "hi max", "oye max"]

@app.post("/api/wake-check")
async def wake_check(request: WakeCheckRequest):
    """
    Lightweight wake word verification.
    Takes audio, runs STT with auto language detect, checks for wake phrases.
    Returns quickly — designed for frequent background checks.
    """
    try:
        transcript = await transcribe_wake_word(request.audio)
        if not transcript:
            return {"wake_detected": False, "transcript": ""}

        transcript_lower = transcript.lower().strip()
        logger.info(f"Wake check transcript: '{transcript_lower}'")

        # Check if any wake phrase is in the transcript
        detected = any(phrase in transcript_lower for phrase in WAKE_PHRASES)

        return {
            "wake_detected": detected,
            "transcript": transcript_lower
        }

    except Exception as e:
        logger.error(f"Wake check failed: {e}")
        return {"wake_detected": False, "transcript": "", "error": str(e)}


# ═══════════════════════════════════════════════════
# WEBSOCKET — Real-time Voice/Text Chat
# ═══════════════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info(f"Client connected: {websocket.client}")

    global active_websocket, main_loop
    active_websocket = websocket
    main_loop = asyncio.get_running_loop()

    agent = get_agent()
    skills = get_skills_engine(config)

    try:
        while True:
            try:
                msg = await websocket.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.error(f"WebSocket receive error: {e}", exc_info=True)
                try:
                    await websocket.send_json({"event": "error", "message": "Backend Error: invalid payload"})
                except Exception:
                    pass
                continue

            try:
                msg_type = msg.get("type", "text")

                # 1. HANDLE GREETING EXPLICITLY (Fixes Double Greeting)
                if msg_type == "request_greeting":
                    greeting = await agent.get_greeting()
                    await websocket.send_json({
                        "event": "greeting",
                        "text": greeting
                    })
                    tts_path = await generate_tts(greeting[:300])
                    if tts_path and os.path.exists(tts_path):
                        try:
                            with open(tts_path, "rb") as f:
                                encoded_audio = base64.b64encode(f.read()).decode('utf-8')
                                await websocket.send_json({
                                    "event": "audio_response",
                                    "audio": encoded_audio
                                })
                        except Exception as e:
                            logger.error(f"Greeting TTS error: {e}")

                # 2. HANDLE TEXT INPUT
                elif msg_type == "text":
                    user_text = msg.get("message", msg.get("text", "")).strip()
                    if not user_text:
                        continue
                    logger.info(f"User Text: {user_text}")

                    # ── Research file follow-up interception (matches voice handler) ──
                    lower_text = user_text.lower().strip()
                    text_follow_up_words = ["haan", "open", "kholo", "yes", "khol", "open it", "haan kholo"]
                    is_text_follow_up = any(word in lower_text for word in text_follow_up_words)

                    text_intercepted = False
                    if is_text_follow_up:
                        import glob
                        import time as _time
                        from modules.web_autopilot import CACHE_DIR

                        # Check both research cache AND code save dir for recently created files
                        files = glob.glob(str(CACHE_DIR / "*.*"))
                        try:
                            code_save_dir = config.CODE_SAVE_DIR
                            if code_save_dir.exists():
                                files.extend(glob.glob(str(code_save_dir / "*.*")))
                        except Exception:
                            pass
                        latest_file = max(files, key=os.path.getmtime) if files else None

                        if latest_file and (_time.time() - os.path.getmtime(latest_file) < 300):
                            logger.info(f"Text follow-up intercepted: Opening latest file: {latest_file}")
                            skills._skill_open_app(latest_file)
                            await websocket.send_json({
                                "event": "response_text",
                                "text": f"Opening file: {os.path.basename(latest_file)}"
                            })
                            text_intercepted = True
                        else:
                            from modules.web_autopilot import LAST_BOT_BYPASS_URL, clear_last_bot_bypass_url
                            if LAST_BOT_BYPASS_URL:
                                logger.info(f"Text follow-up intercepted: Opening bot bypass URL: {LAST_BOT_BYPASS_URL}")
                                skills._skill_web_open(LAST_BOT_BYPASS_URL)
                                await websocket.send_json({
                                    "event": "response_text",
                                    "text": "Opening blocked website on screen..."
                                })
                                clear_last_bot_bypass_url()
                                text_intercepted = True

                    if text_intercepted:
                        continue

                    result = await agent.process_text_input(user_text, use_tts=True, input_source="text")
                    await websocket.send_json({
                        "event": "response_text",
                        "text": result.get("response", ""),
                        "skill_used": result.get("skill_used"),
                    })
                    tts_path = result.get("tts_path", "")
                    if tts_path and os.path.exists(tts_path):
                        try:
                            with open(tts_path, "rb") as f:
                                encoded_audio = base64.b64encode(f.read()).decode('utf-8')
                                await websocket.send_json({
                                    "event": "audio_response",
                                    "audio": encoded_audio
                                })
                        except Exception as e:
                            logger.error(f"Text TTS Read Error: {e}")

                # 3. HANDLE VOICE INPUT
                elif msg_type == "voice" or msg_type == "audio":
                    audio_data = msg.get("audio", msg.get("data", ""))
                    if not audio_data:
                        continue
                    from modules.stt import transcribe_audio
                    transcript = await transcribe_audio(audio_data)

                    # Filter out empty, error, and whisper hallucination transcripts
                    if not transcript or not transcript.strip():
                        logger.info("STT returned empty transcript, skipping LLM")
                        await websocket.send_json({"event": "error", "message": "I didn't catch that. Please try again."})
                        continue

                    lower_trans = transcript.lower().strip()
                    hallucinations = ["thank you.", "thank you", "thanks for watching", "subtitles by amara.org"]
                    if lower_trans in hallucinations:
                        logger.info("STT returned hallucination, skipping LLM")
                        await websocket.send_json({"event": "error", "message": "I didn't catch that. Please try again."})
                        continue


                    logger.info(f"STT: {transcript}")

                    await websocket.send_json({
                        "event": "transcript",
                        "text": transcript
                    })

                    # Intercept conversational follow-ups like "Haan", "Open", "Kholo", "Yes"
                    follow_up_words = ["haan", "open", "kholo", "yes", "khol"]
                    is_follow_up = any(word in lower_trans for word in follow_up_words)
                    
                    intercepted = False
                    if is_follow_up:
                        import glob
                        import time
                        from modules.web_autopilot import CACHE_DIR
                        
                        # Check both research cache AND code save dir for recently created files
                        files = glob.glob(str(CACHE_DIR / "*.*"))
                        try:
                            code_save_dir = config.CODE_SAVE_DIR
                            if code_save_dir.exists():
                                files.extend(glob.glob(str(code_save_dir / "*.*")))
                        except Exception:
                            pass
                        latest_file = max(files, key=os.path.getmtime) if files else None
                        
                        # Check if latest file exists and was created in the last 5 minutes (300s)
                        if latest_file and (time.time() - os.path.getmtime(latest_file) < 300):
                            logger.info(f"Intercepted follow-up: Opening latest file: {latest_file}")
                            skills._skill_open_app(latest_file)
                            await websocket.send_json({
                                "event": "response_text",
                                "text": f"Opening file: {os.path.basename(latest_file)}"
                            })
                            intercepted = True
                        else:
                            # Check for LAST_BOT_BYPASS_URL from web_autopilot
                            from modules.web_autopilot import LAST_BOT_BYPASS_URL, clear_last_bot_bypass_url
                            if LAST_BOT_BYPASS_URL:
                                logger.info(f"Intercepted follow-up: Opening bot bypass URL: {LAST_BOT_BYPASS_URL}")
                                skills._skill_web_open(LAST_BOT_BYPASS_URL)
                                await websocket.send_json({
                                    "event": "response_text",
                                    "text": f"Opening blocked website on screen..."
                                })
                                clear_last_bot_bypass_url()
                                intercepted = True
                                
                    if intercepted:
                        # Halt downstream LLM execution to stop continuous voice listening bleeding
                        continue

                    result = await agent.process_text_input(transcript, use_tts=True, input_source="voice")
                    await websocket.send_json({
                        "event": "response_text",
                        "text": result.get("response", ""),
                        "skill_used": result.get("skill_used"),
                    })
                    tts_path = result.get("tts_path", "")
                    if tts_path and os.path.exists(tts_path):
                        try:
                            with open(tts_path, "rb") as f:
                                encoded_audio = base64.b64encode(f.read()).decode('utf-8')
                                await websocket.send_json({
                                    "event": "audio_response",
                                    "audio": encoded_audio
                                })
                        except Exception as e:
                            logger.error(f"Voice TTS Read Error: {e}")
                # 3.5 HANDLE IMAGE INPUT
                elif msg_type == "image":
                    image_data = msg.get("image_data", "")
                    prompt = msg.get("prompt", "What is in this image?")
                    
                    if not image_data:
                        continue
                        
                    logger.info(f"Received Image for analysis. Prompt: {prompt}")
                    
                    # Ensure base64 string doesn't have the data URI scheme attached
                    if "," in image_data:
                        image_data = image_data.split(",")[1]
                        
                    import uuid
                    # Save base64 to a temporary physical file
                    temp_filepath = config.DATA_DIR / f"temp_vision_{uuid.uuid4().hex}.jpg"
                    
                    try:
                        with open(temp_filepath, "wb") as f:
                            f.write(base64.b64decode(image_data))
                            
                        # Tell the UI we are analyzing it
                        from modules.llm import analyze_image_with_prompt
                        vision_response = await analyze_image_with_prompt(str(temp_filepath), prompt)
                        
                        # Send back the AI response
                        await websocket.send_json({
                            "event": "response_text",
                            "text": vision_response,
                            "skill_used": "vision",
                        })
                        
                        # Trigger TTS so MAX speaks the analysis aloud
                        tts_path = await generate_tts(vision_response[:300])
                        if tts_path and os.path.exists(tts_path):
                            with open(tts_path, "rb") as f:
                                encoded_audio = base64.b64encode(f.read()).decode('utf-8')
                                await websocket.send_json({
                                    "event": "audio_response",
                                    "audio": encoded_audio
                                })
                    except Exception as e:
                        logger.error(f"Vision error: {e}")
                        await websocket.send_json({"event": "error", "message": "Failed to analyze image."})
                    finally:
                        # Ensure temp image is deleted to save space
                        if os.path.exists(temp_filepath):
                            os.remove(temp_filepath)                 

                # 4. KEEPALIVE / PING
                elif msg_type == "ping":
                    await websocket.send_json({"event": "pong"})

                # 5. CLEAR MEMORY
                elif msg_type == "clear_memory":
                    msg_resp = await agent.clear_memory()
                    await websocket.send_json({"type": "system", "text": msg_resp})

                # 5.5 EXECUTE SKILL
                elif msg_type == "execute_skill":
                    skill_name = msg.get("skill")
                    params = msg.get("params", [])
                    if skill_name in skills.skills_registry:
                        try:
                            raw = skills.skills_registry[skill_name](*params)
                            result = await raw if asyncio.iscoroutine(raw) else raw
                            logger.info(f"WebSocket execute_skill {skill_name} result: {result}")
                            await websocket.send_json({
                                "event": "response_text",
                                "text": f"Executed: {result}"
                            })
                        except Exception as e:
                            logger.error(f"WebSocket execute_skill failed: {e}")
                            await websocket.send_json({"event": "error", "message": f"Skill execution failed: {e}"})

                # 6. ABORT / KILL SWITCH
                elif msg_type == "abort":
                    logger.info("Client sent abort signal")
            except Exception as e:
                logger.error(f"WebSocket message error: {e}", exc_info=True)
                try:
                    await websocket.send_json({"event": "error", "message": f"Backend Error: {str(e)}"})
                except Exception:
                    pass
                continue

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"event": "error", "message": f"Backend Error: {str(e)}"})
        except Exception:
            pass
    finally:
        if active_websocket == websocket:
            active_websocket = None


# ═══════════════════════════════════════════════════
# HEALTH & SYSTEM
# ═══════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "4.2.0",
        "timestamp": datetime.now().isoformat(),
        "features": {
            "voice": True,
            "vision": True,
            "code": True,
            "files": True,
            "email": get_email_agent().is_enabled(),
            "calendar": True,
            "browser": True,
            "smarthome": config.IR_BLASTER_ENABLED,
            "plugins": True,
            "clipboard": True,
            "brightness": True,
            "lock": True,
            "wake_word": True,
        },
        "llm_model": config.LLM_MODEL,
        "tts_voice": config.TTS_VOICE,
    }


# ═══════════════════════════════════════════════════
# TTS / STT
# ═══════════════════════════════════════════════════

@app.post("/api/speak")
async def speak(request: TextInput):
    tts_path = await generate_tts(request.text[:300])
    if tts_path and os.path.exists(tts_path):
        with open(tts_path, "rb") as f:
            return {"audio": base64.b64encode(f.read()).decode('utf-8'), "text": request.text}
    return {"error": "TTS generation failed boss."}

@app.post("/api/listen")
async def listen(audio_path: str = ""):
    if not audio_path:
        return {"error": "Audio file path do boss."}
    transcript = await transcribe_file(audio_path)
    return {"transcript": transcript}

@app.post("/api/voice")
async def voice(request: VoiceRequest):
    agent = get_agent()
    transcript = await transcribe_audio(request.audio)
    
    lower_trans = transcript.lower().strip()
    hallucinations = ["thank you.", "thank you", "thanks for watching", "subtitles by amara.org", ""]
    if lower_trans in hallucinations:
        return {
            "transcript": transcript,
            "response": "I didn't catch that. Please try again.",
            "skill_used": None,
        }

    result = await agent.process_text_input(transcript, use_tts=True, input_source="voice")

    response_data = {
        "transcript": transcript,
        "response": result.get("response", ""),
        "skill_used": result.get("skill_used"),
    }

    tts_path = result.get("tts_path", "")
    if tts_path and os.path.exists(tts_path):
        try:
            with open(tts_path, "rb") as f:
                response_data["audio"] = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"Voice TTS Read Error: {e}")

    return response_data


# ═══════════════════════════════════════════════════
# FILE MANAGEMENT
# ═══════════════════════════════════════════════════

@app.get("/api/files/search")
async def search_files(query: str = Query(...)):
    skills = get_skills_engine(config)
    result = skills._skill_search_files(query)
    return {"result": result}

@app.get("/api/files/list")
async def list_files(folder: str = Query(".")):
    skills = get_skills_engine(config)
    result = skills._skill_list_files(folder)
    return {"result": result}

@app.get("/api/files/read")
async def read_file_api(filepath: str = Query(...)):
    skills = get_skills_engine(config)
    result = skills._skill_read_file(filepath)
    return {"result": result}


# ═══════════════════════════════════════════════════
# SCREEN / VISION
# ═══════════════════════════════════════════════════

@app.post("/api/screenshot")
async def screenshot(filename: str = ""):
    skills = get_skills_engine(config)
    result = skills._skill_screenshot(filename)
    return {"result": result}

@app.post("/api/screen/read")
async def read_screen(window: str = ""):
    skills = get_skills_engine(config)
    result = await skills._skill_read_screen(window)
    return {"result": result}


# ═══════════════════════════════════════════════════
# PC CONTROL
# ═══════════════════════════════════════════════════

@app.post("/api/volume")
async def volume(request: VolumeRequest):
    skills = get_skills_engine(config)
    result = skills._skill_volume_control(request.action, str(request.value))
    return {"result": result}

@app.post("/api/open-app")
async def open_app(request: OpenAppRequest):
    skills = get_skills_engine(config)
    result = skills._skill_open_app(request.app_name)
    return {"result": result}

@app.post("/api/open-url")
async def open_url(request: OpenUrlRequest):
    skills = get_skills_engine(config)
    result = skills._skill_web_open(request.url)
    return {"result": result}

@app.post("/api/whatsapp")
async def whatsapp(request: WhatsAppRequest):
    skills = get_skills_engine(config)
    result = skills._skill_whatsapp_message(request.contact, request.message)
    return {"result": result}

@app.post("/api/type-text")
async def type_text(request: TypeTextRequest):
    skills = get_skills_engine(config)
    result = skills._skill_type_text(request.text)
    return {"result": result}

@app.post("/api/timer")
async def timer(request: TimerRequest):
    skills = get_skills_engine(config)
    result = skills._skill_timer(str(request.seconds), request.label)
    return {"result": result}

@app.get("/api/weather")
async def weather(city: str = Query("auto")):
    skills = get_skills_engine(config)
    result = skills._skill_weather(city)
    return {"result": result}

@app.post("/api/shutdown")
async def shutdown(request: ShutdownRequest):
    skills = get_skills_engine(config)
    result = skills._skill_system_shutdown(str(request.delay))
    return {"result": result}

@app.post("/api/restart")
async def restart(request: RestartRequest):
    skills = get_skills_engine(config)
    result = skills._skill_system_restart(str(request.delay))
    return {"result": result}


# ═══════════════════════════════════════════════════
# CODE ENDPOINTS
# ═══════════════════════════════════════════════════

@app.post("/api/generate-code")
async def generate_code(request: CodeRequest):
    skills = get_skills_engine(config)
    result = await skills._skill_write_code(request.language, request.description)
    return {"result": result}

@app.post("/api/run-code")
async def run_code(request: RunCodeRequest):
    skills = get_skills_engine(config)
    result = await skills._skill_run_code(request.filepath)
    return {"result": result}

@app.post("/api/review-code")
async def review_code(request: ReviewCodeRequest):
    skills = get_skills_engine(config)
    result = await skills._skill_code_review(request.filepath)
    return {"result": result}

@app.post("/api/fix-code")
async def fix_code(request: FixCodeRequest):
    skills = get_skills_engine(config)
    result = await skills._skill_fix_code(request.filepath, request.issue)
    return {"result": result}

@app.post("/api/project-scaffold")
async def project_scaffold(request: ProjectScaffoldRequest):
    skills = get_skills_engine(config)
    result = await skills._skill_project_scaffold(request.project_type, request.project_name)
    return {"result": result}


# ═══════════════════════════════════════════════════
# EMAIL ENDPOINTS
# ═══════════════════════════════════════════════════

@app.post("/api/email/send")
async def email_send(request: EmailSendRequest):
    agent = get_email_agent()
    result = agent.send_email(request.to, request.subject, request.body)
    return {"result": result}

@app.get("/api/email/check")
async def email_check():
    agent = get_email_agent()
    result = agent.check_emails()
    return {"result": result}


# ═══════════════════════════════════════════════════
# CALENDAR ENDPOINTS
# ═══════════════════════════════════════════════════

@app.get("/api/calendar/today")
async def calendar_today():
    agent = get_calendar_agent()
    result = agent.today()
    return {"result": result}

@app.get("/api/calendar/week")
async def calendar_week():
    agent = get_calendar_agent()
    result = agent.week()
    return {"result": result}

@app.post("/api/calendar/add")
async def calendar_add(request: CalendarAddRequest):
    agent = get_calendar_agent()
    result = agent.add_event(request.title, request.date, request.time)
    return {"result": result}


# ═══════════════════════════════════════════════════
# BROWSER ENDPOINTS
# ═══════════════════════════════════════════════════

@app.post("/api/browser/open")
async def browser_open(request: BrowserOpenRequest):
    agent = get_browser_agent()
    result = agent.open_url(request.url)
    return {"result": result}

@app.post("/api/browser/click")
async def browser_click(request: BrowserActionRequest):
    agent = get_browser_agent()
    result = agent.click(request.selector)
    return {"result": result}

@app.post("/api/browser/type")
async def browser_type(request: BrowserActionRequest):
    agent = get_browser_agent()
    result = agent.type_text(request.selector, request.text)
    return {"result": result}

@app.post("/api/browser/scrape")
async def browser_scrape(request: BrowserScrapeRequest):
    agent = get_browser_agent()
    result = agent.scrape(request.url, request.query)
    return {"result": result}


# ═══════════════════════════════════════════════════
# SMART HOME ENDPOINTS
# ═══════════════════════════════════════════════════

@app.post("/api/smarthome/fan")
async def smarthome_fan(request: FanRequest):
    agent = get_smarthome_agent()
    result = agent.fan_control(request.action)
    return {"result": result}

@app.post("/api/smarthome/light")
async def smarthome_light(request: LightRequest):
    agent = get_smarthome_agent()
    result = agent.light_control(request.action)
    return {"result": result}

@app.post("/api/smarthome/ac")
async def smarthome_ac(request: ACRequest):
    agent = get_smarthome_agent()
    result = agent.ac_control(request.action, request.value)
    return {"result": result}


# ═══════════════════════════════════════════════════
# PC CONTROL — NEW
# ═══════════════════════════════════════════════════

@app.post("/api/pc/brightness")
async def pc_brightness(request: BrightnessRequest):
    skills = get_skills_engine(config)
    result = skills._skill_brightness(request.action, str(request.value))
    return {"result": result}

@app.post("/api/pc/clipboard")
async def pc_clipboard(request: ClipboardRequest):
    skills = get_skills_engine(config)
    result = skills._skill_clipboard(request.action, request.text)
    return {"result": result}

@app.post("/api/pc/lock")
async def pc_lock():
    skills = get_skills_engine(config)
    result = skills._skill_lock_pc()
    return {"result": result}


# ═══════════════════════════════════════════════════
# PLUGIN ENDPOINTS
# ═══════════════════════════════════════════════════

@app.get("/api/plugins/list")
async def plugins_list():
    loader = get_plugin_loader()
    result = loader.list_plugins()
    return {"result": result}

@app.post("/api/plugins/reload")
async def plugins_reload():
    loader = get_plugin_loader()
    loader.reload()
    skills = get_skills_engine(config)
    skills.skills_registry = skills._register_skills()
    return {"result": "Plugins reload ho gaye."}


# ═══════════════════════════════════════════════════
# TEXT CHAT (non-WebSocket fallback)
# ═══════════════════════════════════════════════════

@app.post("/api/chat")
async def chat(request: TextInput):
    agent = get_agent()
    result = await agent.process_text_input(request.text, use_tts=request.tts, input_source="text")
    response_data = {
        "response": result.get("response", ""),
        "skill_used": result.get("skill_used"),
    }
    tts_path = result.get("tts_path", "")
    if tts_path and os.path.exists(tts_path):
        try:
            with open(tts_path, "rb") as f:
                response_data["audio"] = base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Chat REST TTS Read Error: {e}")
    return response_data


# ═══════════════════════════════════════════════════
# KNOWLEDGE BASE ENDPOINTS
# ═══════════════════════════════════════════════════

class KBRebuildRequest(BaseModel):
    pass

class KBAddRequest(BaseModel):
    filename: str
    content: str

@app.post("/api/kb/rebuild")
async def kb_rebuild():
    kb = get_knowledge_base(config)
    result = kb.build_index()
    return {"result": result}

@app.get("/api/kb/list")
async def kb_list():
    kb = get_knowledge_base(config)
    return {"result": kb.list_documents()}

@app.get("/api/kb/stats")
async def kb_stats():
    kb = get_knowledge_base(config)
    return {"result": kb.get_stats()}

@app.get("/api/kb/search")
async def kb_search(query: str = Query(...)):
    kb = get_knowledge_base(config)
    ctx = kb.query(query, top_k=5, min_similarity=0.20)
    return {"result": ctx or "No relevant results found."}

@app.post("/api/kb/add")
async def kb_add(request: KBAddRequest):
    kb = get_knowledge_base(config)
    result = kb.add_document(request.filename, request.content)
    return {"result": result}


# ═══════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info(f"MAX v4.2 starting on {config.HOST}:{config.PORT}")
    logger.info(f"   LLM: {config.LLM_MODEL}")
    logger.info(f"   TTS: {config.TTS_VOICE}")
    logger.info(f"   Skills: {len(get_skills_engine(config).skills_registry)} registered")
    logger.info(f"   Wake word: enabled")

    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
        reload_excludes=["*.json", "data/*", "knowledge/*"],
        log_level="info" if not config.DEBUG else "debug",
    )
