"""
main_startup_patch.py
=====================
Yeh code apne main.py mein add karo.

Step 1: app = FastAPI(...) ke BAAD, routes se PEHLE yeh block paste karo.
Step 2: Bas. Done.

Context: This starts the reminder daemon and auto-indexes the knowledge base
         every time the server starts.
"""

# ── PASTE THIS INTO main.py (after app = FastAPI(...)) ──────────────────────



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
        logger.info("✅ Reminder daemon started")
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


# ── ALSO ADD THESE REST ENDPOINTS for KB (after existing endpoints) ──────────

from modules.knowledge_base import get_knowledge_base   # add to imports at top


class KBRebuildRequest(BaseModel):
    pass


class KBAddRequest(BaseModel):
    filename: str
    content:  str


@app.post("/api/kb/rebuild")
async def kb_rebuild():
    """Rebuild full knowledge base index from .md files."""
    kb     = get_knowledge_base(config)
    result = kb.build_index()
    return {"result": result}


@app.get("/api/kb/list")
async def kb_list():
    """List all .md files in knowledge base."""
    kb = get_knowledge_base(config)
    return {"result": kb.list_documents()}


@app.get("/api/kb/stats")
async def kb_stats():
    """Knowledge base statistics."""
    kb = get_knowledge_base(config)
    return {"result": kb.get_stats()}


@app.get("/api/kb/search")
async def kb_search(query: str = Query(...)):
    """Manual knowledge base search."""
    kb  = get_knowledge_base(config)
    ctx = kb.query(query, top_k=5, min_similarity=0.20)
    return {"result": ctx or "No relevant results found."}


@app.post("/api/kb/add")
async def kb_add(request: KBAddRequest):
    """Add a single document to the knowledge base."""
    kb     = get_knowledge_base(config)
    result = kb.add_document(request.filename, request.content)
    return {"result": result}

# ────────────────────────────────────────────────────────────────────────────
