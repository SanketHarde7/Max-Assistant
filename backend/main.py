"""
main.py — JARVIS v4.0
Backend: FastAPI + WebSocket + REST endpoints.
Fixed: Adapted precisely for Frontend events (request_greeting, audio_response) and RAW Base64.
"""
import os
import sys
import logging
import base64
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
from modules.stt import transcribe_audio, transcribe_file
from modules.tts import generate_tts
from modules.llm import get_greeting
from modules.skills import get_skills_engine
from modules.memory import get_memory_manager
from modules.email_agent import get_email_agent
from modules.calendar_agent import get_calendar_agent
from modules.browser_agent import get_browser_agent
from modules.smarthome_agent import get_smarthome_agent
from modules.plugin_loader import get_plugin_loader

# ═══════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO if not config.DEBUG else logging.DEBUG,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("JARVIS.API")

# ═══════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════

app = FastAPI(
    title="JARVIS API",
    description="Sanket's AI Assistant Backend",
    version="4.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════

class TextInput(BaseModel):
    text: str
    tts: bool = True

class VoiceRequest(BaseModel):
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
    action: str = "up"   # up, down, mute, set
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
    date: str   # YYYY-MM-DD
    time: str = ""   # HH:MM

class BrowserOpenRequest(BaseModel):
    url: str

class BrowserActionRequest(BaseModel):
    selector: str
    text: str = ""

class BrowserScrapeRequest(BaseModel):
    url: str
    query: str

class FanRequest(BaseModel):
    action: str   # on, off, speed1-5, swing

class LightRequest(BaseModel):
    action: str   # on, off

class ACRequest(BaseModel):
    action: str   # on, off, temp
    value: str = ""

class BrightnessRequest(BaseModel):
    action: str   # up, down, set
    value: int = 10

class ClipboardRequest(BaseModel):
    action: str   # get, set
    text: str = ""

# ═══════════════════════════════════════════════════
# WEBSOCKET — Real-time Voice/Text Chat
# ═══════════════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info(f"Client connected: {websocket.client}")

    agent = get_agent()
    skills = get_skills_engine(config)

    try:
        # NOTE: Initial connection block removed.
        # We now wait for frontend to explicitly send 'request_greeting'

        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type", "text")

            # 1. HANDLE GREETING EXPLICITLY (Fixes Double Greeting)
            if msg_type == "request_greeting":
                greeting = await agent.get_greeting()
                
                # Send text first to update UI
                await websocket.send_json({
                    "event": "greeting",
                    "text": greeting
                })

                # Generate TTS and send in separate event
                tts_path = await generate_tts(greeting[:300])
                if tts_path and os.path.exists(tts_path):
                    try:
                        with open(tts_path, "rb") as f:
                            # Send RAW base64, frontend appends 'data:'
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

                result = await agent.process_text_input(user_text, use_tts=True)
                
                # Send text response first
                await websocket.send_json({
                    "event": "response_text",
                    "text": result.get("response", ""),
                    "skill_used": result.get("skill_used"),
                })

                # Send audio in dedicated audio_response event (Fixes Voice Playback)
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
                # Frontend sends audio as base64 in 'audio' or 'data' key
                audio_data = msg.get("audio", msg.get("data", ""))
                if not audio_data:
                    continue
                
                from modules.stt import transcribe_audio
                transcript = await transcribe_audio(audio_data)
                logger.info(f"STT: {transcript}")

                # Send transcript to UI immediately
                await websocket.send_json({
                    "event": "transcript",
                    "text": transcript
                })

                result = await agent.process_text_input(transcript, use_tts=True)
                
                # Send text response
                await websocket.send_json({
                    "event": "response_text",
                    "text": result.get("response", ""),
                    "skill_used": result.get("skill_used"),
                })

                # Send audio response
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

            # 4. KEEPALIVE / PING
            elif msg_type == "ping":
                await websocket.send_json({"event": "pong"})
                
            # 5. CLEAR MEMORY
            elif msg_type == "clear_memory":
                msg_resp = await agent.clear_memory()
                await websocket.send_json({"type": "system", "text": msg_resp})
                
            # 6. ABORT / KILL SWITCH
            elif msg_type == "abort":
                logger.info("🛑 Client sent abort signal")

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"event": "error", "message": f"Backend Error: {str(e)}"})
        except Exception:
            pass

# ═══════════════════════════════════════════════════
# HEALTH & SYSTEM
# ═══════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "4.0.0",
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
            # RAW Base64 ONLY
            return {"audio": base64.b64encode(f.read()).decode('utf-8'), "text": request.text}
    return {"error": "TTS generation failed bhai."}

@app.post("/api/listen")
async def listen(audio_path: str = ""):
    if not audio_path:
        return {"error": "Audio file path do bhai."}
    transcript = await transcribe_file(audio_path)
    return {"transcript": transcript}

@app.post("/api/voice")
async def voice(request: VoiceRequest):
    agent = get_agent()
    transcript = await transcribe_audio(request.audio)
    result = await agent.process_text_input(transcript, use_tts=True)

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
async def read_file(filepath: str = Query(...)):
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
    return {"result": "Plugins reload ho gaye bhai."}

# ═══════════════════════════════════════════════════
# TEXT CHAT (non-WebSocket fallback)
# ═══════════════════════════════════════════════════

@app.post("/api/chat")
async def chat(request: TextInput):
    agent = get_agent()
    # Handle 'message' or 'text' gracefully for REST fallback
    result = await agent.process_text_input(request.text, use_tts=request.tts)
    
    response_data = {
        "response": result.get("response", ""),
        "skill_used": result.get("skill_used"),
    }
    
    tts_path = result.get("tts_path", "")
    if tts_path and os.path.exists(tts_path):
        try:
            with open(tts_path, "rb") as f:
                # RAW Base64 ONLY
                response_data["audio"] = base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Chat REST TTS Read Error: {e}")

    return response_data

# ═══════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info(f"🚀 JARVIS v4.0 starting on {config.HOST}:{config.PORT}")
    logger.info(f"   LLM: {config.LLM_MODEL}")
    logger.info(f"   TTS: {config.TTS_VOICE}")
    logger.info(f"   Skills: {len(get_skills_engine(config).skills_registry)} registered")

    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
        log_level="info" if not config.DEBUG else "debug",
    )