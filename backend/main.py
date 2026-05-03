"""
JARVIS AI Assistant v3.0 — Enhanced Backend
FastAPI + WebSocket with agent-level skills support.

Pipeline: STT → Memory → LLM → Skills (Code/File/PC) → TTS
"""
import logging
import base64
import json
import asyncio
import traceback
from datetime import datetime
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

from config import config
from modules import stt, llm, tts
from modules.memory import get_memory_manager
from modules.skills import get_skills_engine
from modules.code_engine import get_code_engine
from modules.file_manager import get_file_manager
from modules.agent_core import get_agent_core

# ═══════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
)
logger = logging.getLogger("JARVIS.CORE")

# ═══════════════════════════════════════════
# Singleton Managers
# ═══════════════════════════════════════════

memory_manager = None
skills_engine = None
code_engine = None
file_manager = None
agent_core = None
SEARCH_DATA_SKILLS = {"search", "weather"}  # These get 2nd LLM pass for summarization

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/Shutdown lifecycle."""
    global memory_manager, skills_engine, code_engine, file_manager, agent_core
    logger.info("🚀 JARVIS v3.0 Initializing...")

    try:
        memory_manager = get_memory_manager(config)
        logger.info(f"💾 Memory: {config.MEMORY_FILE}")

        if config.SKILLS_ENABLED:
            skills_engine = get_skills_engine(config)
            logger.info(f"🔧 Skills: {len(skills_engine.skills_registry)} skills loaded")

        code_engine = get_code_engine(config)
        logger.info(f"💻 Code Engine: workspace={config.WORKSPACE_DIR}")

        file_manager = get_file_manager(config)
        logger.info(f"📁 File Manager: {len(config.SEARCH_DIRS)} search dirs")

        agent_core = get_agent_core(config)
        logger.info(f"🧠 Agent Core: planning enabled")

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        logger.error(traceback.format_exc())
        raise

    yield
    logger.info("🔌 JARVIS shutting down.")


app = FastAPI(title="JARVIS AI Assistant", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════
# Request Models
# ═══════════════════════════════════════════

class VoiceRequest(BaseModel):
    audio: str  # base64

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class CodeRequest(BaseModel):
    description: str
    language: str = "auto"

class RunCodeRequest(BaseModel):
    filepath: str

class ExplainRequest(BaseModel):
    filename: str
    context: str = ""

class EditRequest(BaseModel):
    filepath: str
    old_text: str
    new_text: str


# ═══════════════════════════════════════════
# Response Builder
# ═══════════════════════════════════════════

async def _handle_skill_result(
    user_text: str,
    response_text: str,
    skill_result: dict,
    context: str
) -> str:
    """
    Smart skill result handler.

    - SEARCH/WEATHER skills → 2nd LLM pass → conversational summary
    - Other DATA skills → truncated result appended
    - ACTION skills → LLM response as-is (already says what it did)
    """
    if not skill_result.get("executed"):
        return response_text

    skill_name = skill_result.get("skill_name", "")
    result_str = skill_result.get("result", "").strip()
    tts_result = skill_result.get("tts_result", "").strip()
    is_data = skill_result.get("is_data_skill", False)

    if not is_data:
        return response_text

    if skill_name in SEARCH_DATA_SKILLS and result_str:
        try:
            summary = await llm.get_response_with_skill_result(
                user_text=user_text,
                skill_result_text=result_str,
                memory_context=context
            )
            return summary["response"]
        except Exception as e:
            logger.warning(f"2nd LLM pass failed: {e}")
            return f"{response_text} {tts_result}".strip()

    if tts_result:
        return f"{response_text} {tts_result}".strip()

    return response_text



# ═══════════════════════════════════════════
# PIPELINES
# ═══════════════════════════════════════════

async def run_voice_pipeline(audio_bytes: bytes) -> dict:
    """Full Voice: STT → Memory → LLM → Skills → TTS"""
    global memory_manager, skills_engine, code_engine

    # 1. STT
    logger.info(f"🎙️ STT ({len(audio_bytes)} bytes)...")
    transcript = await asyncio.wait_for(
        stt.transcribe_audio(audio_bytes), timeout=30.0
    )
    if not transcript or not transcript.strip():
        raise ValueError("Kuch sunai nahi diya sir. Saaf boliye.")
    logger.info(f"✅ STT: '{transcript}'")

    # 2. Memory
    if memory_manager:
        await asyncio.wait_for(
            memory_manager.add_message("user", transcript), timeout=10.0
        )

    # 3. LLM
    logger.info("🤖 LLM...")
    context = memory_manager.get_context() if memory_manager else ""
    llm_result = await asyncio.wait_for(
        llm.get_response(transcript, memory_context=context), timeout=45.0
    )
    response_text = llm_result["response"]
    logger.info(f"✅ LLM: '{response_text[:100]}'")

    # 4. Skills
    skill_name = None
    skill_result = {"executed": False}

    if skills_engine and llm_result.get("skill"):
        raw_skill_tag = llm_result["skill"]
        logger.info(f"⚙️ Skill: {raw_skill_tag}")
        try:
            skill_result = await skills_engine.parse_and_execute(raw_skill_tag)
            if skill_result.get("executed"):
                skill_name = skill_result.get("skill_name")
                logger.info(f"✅ Skill: {skill_name} → {skill_result.get('result', '')[:80]}")
                response_text = await _handle_skill_result(transcript, response_text, skill_result, context)

                if memory_manager and skill_result.get("result"):
                    await memory_manager.add_message(
                        "system", f"[SKILL_RESULT:{skill_name}] {skill_result['result']}"
                    )
            else:
                logger.warning(f"⚠️ Skill fail: {skill_result.get('error', 'unknown')}")
        except Exception as skill_err:
            logger.warning(f"⚠️ Skill error: {skill_err}")

    # 5. Save response
    if memory_manager:
        await asyncio.wait_for(
            memory_manager.add_message("assistant", response_text), timeout=10.0
        )

    # 6. TTS
    logger.info("🔊 TTS...")
    audio_data = await asyncio.wait_for(
        tts.text_to_speech(response_text), timeout=30.0
    )
    audio_b64 = base64.b64encode(audio_data).decode("utf-8") if audio_data else ""
    logger.info(f"✅ TTS: {len(audio_data)} bytes")

    return {
        "transcript": transcript,
        "response": response_text,
        "skill": skill_name,
        "audio": audio_b64,
    }


async def run_text_pipeline(message: str) -> dict:
    """Text-only: Memory → LLM → Skills → TTS"""
    global memory_manager, skills_engine, code_engine

    if memory_manager:
        await memory_manager.add_message("user", message)

    context = memory_manager.get_context() if memory_manager else ""
    llm_result = await llm.get_response(message, memory_context=context)
    response_text = llm_result["response"]

    skill_name = None
    skill_result = {"executed": False}

    if skills_engine and llm_result.get("skill"):
        try:
            skill_result = await skills_engine.parse_and_execute(llm_result["skill"])
            if skill_result.get("executed"):
                skill_name = skill_result.get("skill_name")
                response_text = await _handle_skill_result(message, response_text, skill_result, context)
                if memory_manager and skill_result.get("result"):
                    await memory_manager.add_message(
                        "system", f"[SKILL_RESULT:{skill_name}] {skill_result['result']}"
                    )
        except Exception:
            pass

    if memory_manager:
        await memory_manager.add_message("assistant", response_text)

    audio_data = await tts.text_to_speech(response_text)
    audio_b64 = base64.b64encode(audio_data).decode("utf-8") if audio_data else ""

    return {
        "response": response_text,
        "skill": skill_name,
        "audio": audio_b64,
    }


# ═══════════════════════════════════════════
# REST ENDPOINTS
# ═══════════════════════════════════════════

@app.post("/api/voice")
async def process_voice(request: VoiceRequest):
    """Full voice pipeline."""
    try:
        audio_bytes = base64.b64decode(request.audio)
        if len(audio_bytes) < 512:
            raise HTTPException(status_code=400, detail="Audio too short")
        result = await run_voice_pipeline(audio_bytes)
        return {"status": "success", **result}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Voice error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def text_chat(request: ChatRequest):
    """Text chat with TTS."""
    try:
        result = await run_text_pipeline(request.message)
        return {"status": "success", "session_id": request.session_id, **result}
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/memory")
async def get_memory():
    if not memory_manager:
        raise HTTPException(status_code=503, detail="Memory not initialized")
    return {
        "messages": memory_manager.memory.get("messages", []),
        "summary": memory_manager.memory.get("summary", ""),
        "user_facts": memory_manager.memory.get("user_facts", {}),
    }


@app.delete("/api/memory")
async def clear_memory():
    if not memory_manager:
        raise HTTPException(status_code=503, detail="Memory not initialized")
    success = await memory_manager.clear_memory()
    return {"success": success}


@app.get("/api/skills")
async def list_skills():
    if not skills_engine:
        return {"skills": [], "enabled": False}
    return {
        "skills": list(skills_engine.skills_registry.keys()),
        "enabled": True,
        "count": len(skills_engine.skills_registry),
    }


@app.get("/api/status")
async def health_check():
    return {
        "status": "ok",
        "version": "3.0.0",
        "model": config.LLM_MODEL,
        "tts_voice": config.TTS_VOICE,
        "memory": "initialized" if memory_manager else "pending",
        "skills": len(skills_engine.skills_registry) if skills_engine else 0,
        "workspace": str(config.WORKSPACE_DIR),
        "code_dir": str(config.CODE_SAVE_DIR),
    }


# ═══════════════════════════════════════════
# NEW v3.0 ENDPOINTS — Direct Skill Access
# ═══════════════════════════════════════════

@app.post("/api/code/write")
async def write_code_endpoint(request: CodeRequest):
    """Direct code generation endpoint."""
    try:
        if not code_engine:
            raise HTTPException(status_code=503, detail="Code engine not ready")
        result = await code_engine.write_code(request.language, request.description)
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"write_code error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/code/run")
async def run_code_endpoint(request: RunCodeRequest):
    """Direct code execution endpoint."""
    try:
        if not code_engine:
            raise HTTPException(status_code=503, detail="Code engine not ready")
        result = await code_engine.run_code(request.filepath)
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"run_code error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/code/review")
async def code_review_endpoint(request: RunCodeRequest):
    """Direct code review endpoint."""
    try:
        if not code_engine:
            raise HTTPException(status_code=503, detail="Code engine not ready")
        result = await code_engine.code_review(request.filepath)
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"code_review error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/files/explain")
async def explain_file_endpoint(request: ExplainRequest):
    """Direct file explanation endpoint."""
    try:
        if not file_manager:
            raise HTTPException(status_code=503, detail="File manager not ready")
        result = await file_manager.find_and_explain(request.filename, request.context)
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"explain error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/files/list")
async def list_files_endpoint(folder: str = ""):
    """Direct file listing endpoint."""
    try:
        if not file_manager:
            raise HTTPException(status_code=503, detail="File manager not ready")
        target = folder or str(config.WORKSPACE_DIR)
        result = await file_manager.list_files(target)
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"list_files error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/files/edit")
async def edit_file_endpoint(request: EditRequest):
    """Direct file edit endpoint."""
    try:
        if not file_manager:
            raise HTTPException(status_code=503, detail="File manager not ready")
        result = await file_manager.edit_file(request.filepath, request.old_text, request.new_text)
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"edit_file error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workspace")
async def get_workspace_info():
    """Get workspace configuration."""
    return {
        "workspace_dir": str(config.WORKSPACE_DIR),
        "code_save_dir": str(config.CODE_SAVE_DIR),
        "search_dirs": [str(d) for d in config.SEARCH_DIRS],
        "max_file_size_kb": config.MAX_FILE_SIZE_KB,
        "project_templates": list(config.PROJECT_TEMPLATES.keys()),
        "code_languages": list(config.CODE_LANGUAGES.keys()),
    }


# ═══════════════════════════════════════════
# AGENT ENDPOINTS (NEW v3.0)
# ═══════════════════════════════════════════

class AgentPlanRequest(BaseModel):
    request: str

class AgentLearnRequest(BaseModel):
    original: str
    correction: str

@app.post("/api/agent/plan")
async def agent_plan(request: AgentPlanRequest):
    """Create task plan from user request."""
    try:
        if not agent_core:
            raise HTTPException(status_code=503, detail="Agent core not ready")
        plan = await agent_core.plan_and_execute(request.request)
        return {"status": "success", "plan": plan.to_dict()}
    except Exception as e:
        logger.error(f"Agent plan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/learn")
async def agent_learn(request: AgentLearnRequest):
    """Teach JARVIS a correction."""
    try:
        if not agent_core:
            raise HTTPException(status_code=503, detail="Agent core not ready")
        agent_core.learn_correction(request.original, request.correction)
        return {"status": "success", "message": "Correction learned sir."}
    except Exception as e:
        logger.error(f"Agent learn error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agent/stats")
async def agent_stats():
    """Get agent learning statistics."""
    try:
        if not agent_core:
            raise HTTPException(status_code=503, detail="Agent core not ready")
        return {"status": "success", "stats": agent_core.get_task_stats()}
    except Exception as e:
        logger.error(f"Agent stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
# WEBSOCKET
# ═══════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("🔌 WebSocket connected")

    async def send(event: str, **data):
        try:
            await websocket.send_json({"event": event, **data})
        except Exception:
            pass

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await send("error", message="Invalid JSON")
                continue

            msg_type = data.get("type", "")

            if msg_type == "request_greeting":
                try:
                    greeting = await llm.get_greeting()
                    audio = await tts.text_to_speech(greeting)
                    audio_b64 = base64.b64encode(audio).decode() if audio else ""
                    await send("response_text", text=greeting)
                    await send("status_update", state="speaking")
                    if audio_b64:
                        await send("audio_response", audio=audio_b64)
                except Exception as e:
                    logger.warning(f"Greeting failed: {e}")
                continue

            if msg_type == "ping":
                await send("pong")
                continue

            if msg_type == "voice":
                audio_b64 = data.get("audio", "")
                if not audio_b64:
                    await send("error", message="No audio data")
                    continue
                try:
                    await send("status_update", state="thinking")
                    audio_bytes = base64.b64decode(audio_b64)
                    if len(audio_bytes) < 512:
                        await send("error", message="Audio too short")
                        await send("status_update", state="idle")
                        continue

                    result = await run_voice_pipeline(audio_bytes)
                    await send("transcript", text=result["transcript"])
                    await send("response_text", text=result["response"])
                    if result.get("skill"):
                        await send("skill_event", skill=result["skill"])
                    await send("status_update", state="speaking")
                    if result.get("audio"):
                        await send("audio_response", audio=result["audio"])
                except asyncio.TimeoutError:
                    await send("error", message="Timeout")
                    await send("status_update", state="idle")
                except Exception as e:
                    logger.error(f"WS voice error: {e}")
                    await send("error", message=str(e))
                    await send("status_update", state="idle")

            elif msg_type == "text":
                message = data.get("message", "").strip()
                if not message:
                    await send("error", message="Empty message")
                    continue
                try:
                    await send("status_update", state="thinking")
                    result = await run_text_pipeline(message)
                    await send("response_text", text=result["response"])
                    if result.get("skill"):
                        await send("skill_event", skill=result["skill"])
                    await send("status_update", state="speaking")
                    if result.get("audio"):
                        await send("audio_response", audio=result["audio"])
                except Exception as e:
                    logger.error(f"WS text error: {e}")
                    await send("error", message=str(e))
                    await send("status_update", state="idle")

            elif msg_type == "code_write":
                description = data.get("description", "")
                language = data.get("language", "auto")
                if not description:
                    await send("error", message="No description")
                    continue
                try:
                    await send("status_update", state="thinking")
                    result = await code_engine.write_code(language, description)
                    await send("skill_event", skill="write_code", data=result)
                    await send("status_update", state="idle")
                except Exception as e:
                    await send("error", message=str(e))
                    await send("status_update", state="idle")

            elif msg_type == "code_run":
                filepath = data.get("filepath", "")
                if not filepath:
                    await send("error", message="No filepath")
                    continue
                try:
                    await send("status_update", state="thinking")
                    result = await code_engine.run_code(filepath)
                    await send("skill_event", skill="run_code", data=result)
                    await send("status_update", state="idle")
                except Exception as e:
                    await send("error", message=str(e))
                    await send("status_update", state="idle")

            elif msg_type == "file_explain":
                filename = data.get("filename", "")
                context = data.get("context", "")
                if not filename:
                    await send("error", message="No filename")
                    continue
                try:
                    await send("status_update", state="thinking")
                    result = await file_manager.find_and_explain(filename, context)
                    await send("skill_event", skill="find_and_explain", data=result)
                    await send("status_update", state="idle")
                except Exception as e:
                    await send("error", message=str(e))
                    await send("status_update", state="idle")

            elif msg_type == "list_files":
                folder = data.get("folder", "")
                try:
                    await send("status_update", state="thinking")
                    result = await file_manager.list_files(folder)
                    await send("skill_event", skill="list_files", data=result)
                    await send("status_update", state="idle")
                except Exception as e:
                    await send("error", message=str(e))
                    await send("status_update", state="idle")

            else:
                await send("error", message=f"Unknown type: {msg_type}")

    except WebSocketDisconnect:
        logger.info("🔌 WebSocket disconnected")
    except Exception as e:
        logger.error(f"WS fatal: {e}")