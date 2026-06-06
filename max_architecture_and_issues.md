# MAX Architecture, Request Flow, & Timeout Diagnostics

This document outlines the end-to-end request processing flow of MAX, its architectural layout, and a comprehensive analysis of the potential issues causing the `"Taking too long. Try again."` timeout message when multiple commands are triggered in rapid succession.

---

## 1. Request Flow Diagram

The diagram below visualizes the life cycle of a voice request from the Tauri Desktop app to the backend modules and external APIs.

```mermaid
sequence-sequence
autonumber

actor User
participant Client as Tauri App (App.tsx)
participant WS as main.py (WebSockets)
participant STT as modules/stt.py (Groq Whisper)
participant Agent as agent_core.py (MaxAgent)
participant Intent as modules/Intent_engine.py
participant KB as modules/knowledge_base.py (ChromaDB)
participant LLM as modules/llm.py (Groq LLM)
participant Skills as modules/skills.py (SkillsEngine)

User->>Client: Triggers Voice Command
Client->>WS: ws.send("type": "voice", "audio": "...", "command_id": "cmd_1")
Note over WS: If cmd_0 is still active,\nWS.cancel(active_task_0)
WS->>STT: transcribe_audio(audio)
STT->>WS: Returns Text Transcript
WS->>Client: Send "event": "transcript"
WS->>Agent: process_text_input(transcript)
Agent->>Intent: classify(transcript)
Intent->>Agent: Intent (COMMAND/CONVERSATION)
Agent->>KB: query(transcript) (sentence-transformers)
KB->>Agent: Injects context chunks
Agent->>LLM: get_response(transcript, combined_context)
LLM->>Agent: Returns Text + [SKILL:tag]
Agent->>Skills: parse_and_execute([SKILL:tag])
Skills->>Agent: Returns Skill Execution Output
Agent->>WS: Return Response + TTS path
WS->>Client: Send "response_text" + "audio_response"
Client->>User: Play voice reply & update Orb UI
```

---

## 2. Request Handling Pipeline (Step-by-Step)

1. **Client Event Triggers**: The Tauri desktop client overlay (`max-desktop`) records audio or captures text, generates a unique `command_id` (e.g., `cmd_123`), and transmits it over WebSockets to `/ws`.
2. **Connection State Management**: The backend (`main.py`) checks if a task is already processing. If so, it issues a `cancel()` on the active `asyncio` task, then creates a new one to process the new request.
3. **Speech-to-Text (STT) Transcription**: The incoming audio is converted into WAV format (using `ffmpeg` fallback if necessary), then uploaded to **Groq Cloud Whisper (`whisper-large-v3`)** for fast, multilingual transcription.
4. **Intent Classification (First-Pass)**: Before querying main response layers, the input goes through the `IntentEngine` (`modules/Intent_engine.py`):
   - **Layer 1**: Quick Regex matching for known conversation patterns or capabilities (takes 0ms).
   - **Layer 2**: Strict LLM classification (Groq, `temperature=0.0`, `max_tokens=80`) to parse commands, information requests, or greetings into JSON.
5. **RAG / Local Knowledge Base Injection**: If the intent allows for skills/searches, the query is passed to `KnowledgeBase.query()` (`modules/knowledge_base.py`). The query is embedded **locally** using the `all-MiniLM-L6-v2` model from `sentence-transformers` on the host CPU. If semantic matches are found in the local ChromaDB database, they are injected into the context.
6. **Main LLM & Skill Parsing**: The query and combined context are sent to the main LLM (`modules/llm.py`):
   - Generates the clean text response.
   - Extracts skill tags (e.g., `[SKILL:open_app:notepad]`).
7. **Skill Dispatcher Execution**: If skill tags are present, they are parsed and dispatched to `SkillsEngine` (`modules/skills.py`). If the skill is a data skill (requires feedback/summary), it makes a secondary LLM call (`get_response_with_skill_result`) to summarize the action.
8. **TTS Generation & WS Delivery**: The final text is sent to the Text-to-Speech generation module, saved as a temp audio file, read into base64, and pushed via WS along with the text response.

---

## 3. Diagnostics: Why Rapid Multiple Commands Cause Timeouts

The error `"Taking too long. Try again."` is explicitly raised when the main LLM call in `modules/llm.py` exceeds its `30.0` second timeout window (`asyncio.wait_for(..., timeout=30.0)`). 

Here are the root-cause mechanisms triggering this issue:

### Issue A: Event Loop Blocking via Local Embedding Generation (ChromaDB)
- **Problem**: When a user inputs commands, the backend queries the local vector database (`knowledge_base.py`). The embedding generation uses `sentence-transformers` (which runs CPU-heavy machine learning calculations in Python).
- **Mechanism**: Python's GIL (Global Interpreter Lock) combined with synchronous CPU execution means `collection.query` blocks the entire FastAPI event loop thread. If the CPU is busy transcribing or generating embeddings, **asyncio cannot process any network sockets or timing events**.
- **Result**: The loop freezes. By the time it resumes, the `asyncio.wait_for` timer for the Groq HTTP connection has expired, immediately raising `TimeoutError`.

### Issue B: The Sync-to-Async Pipeline Bottleneck in Skills
- **Problem**: Several system skills (like `resolve_accurate_url_sync`, local application launching, file parsing, and screenshot creation) are implemented as standard synchronous Python functions.
- **Mechanism**: The skills dispatcher runs `result = await raw if asyncio.iscoroutine(raw) else raw` inside the event loop. If `raw` is a blocking sync function (such as `httpx.Client.get` making an HTTP call with a 4.0s timeout inside `resolve_accurate_url_sync`), the event loop blocks entirely.
- **Result**: Other concurrent requests wait in the TCP/WebSocket queue, exhausting their 30-second timers before they even begin executing.

### Issue C: Cancelled Tasks Continue Blocking the Thread
- **Problem**: When a new command arrives, the backend cancels the previous running task:
  ```python
  active_task = connection_state.get("active_task")
  if active_task and not active_task.done():
      active_task.cancel()
  ```
- **Mechanism**: `active_task.cancel()` only schedules cancellation; it raises `CancelledError` at the next `await` point. If the old task is currently stuck inside a synchronous block (like `ffmpeg` conversion, local embeddings, or synchronous web requests), it **cannot be interrupted** until that synchronous code returns.
- **Result**: The cancelled task keeps hogging the single CPU thread, keeping the new task queued up.

### Issue D: API Key Rate Limits & Rotation Lockups
- **Problem**: Triggering multiple requests in rapid succession makes multiple rapid completions calls to the Groq API.
- **Mechanism**: If you hit Groq's rate limits (TPM/RPM limits), the request is either queued by Groq or fails with a 429 status. If a 429 occurs, `llm.py` rotates the API key and retries:
  ```python
  if "429" in str(e) or "rate limit" in str(e).lower():
      if config.rotate_api_key():
          return await api_call_func()
  ```
- **Result**: If the keys in the rotation pool are also rate-limited or exhausted, this retry logic cascades, easily taking more than 30 seconds to fail, resulting in a timeout.

---

## 4. Suggested Fixes & architectural Improvements

To eliminate the timeout error during concurrent or rapid commands, we should consider implementing the following:

1. **Offload Local Embeddings to a Thread Pool**:
   Change synchronous database queries to run in a thread pool so they don't lock the asyncio event loop:
   ```python
   kb_ctx = await asyncio.to_thread(
       get_knowledge_base(self.config).query, text, top_k=3, min_similarity=0.30
   )
   ```
2. **Move Synchronous Skills to Thread Pools**:
   Identify blocking skills (like URL resolution, screen capturing, file searching) and run them using `asyncio.to_thread` or convert them to native async implementations.
3. **Introduce a Task Queue instead of Simple Cancellation**:
   Instead of canceling and immediately spawning, use a FIFO queue with a short delay to debounce overlapping audio inputs, preventing rate-limiting collisions on Groq's APIs.
4. **Increase Groq API Timeout Easing**:
   Fine-tune retry backoffs and implement immediate failure on hard rate limits rather than long blocking loops.
