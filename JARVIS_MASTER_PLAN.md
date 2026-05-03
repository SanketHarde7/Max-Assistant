# 🤖 PROJECT JARVIS — MASTER PLAN
> Personal AI Voice Assistant | Groq-Powered | Zero Budget | Built by Sanket

---

## 📌 VISION

Ek fully voice-controlled personal AI assistant jo:
- **Sunata hai** (STT via Groq Whisper)
- **Sochta hai** (LLM via Groq llama-3.3-70b)
- **Bolta hai** (TTS via Edge-TTS)
- **Yaad rakhta hai** (Persistent memory/context)
- **Kaam karta hai** (Skills/plugins system)
- **Dikhta hai** (Jarvis-style holographic UI)

---

## 🏗️ SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────┐
│                     FRONTEND (React + Vite)              │
│  ┌─────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │  Orb    │  │  Chat Panel  │  │  Waveform          │  │
│  │ Visual  │  │  + Transcript│  │  Visualizer        │  │
│  └─────────┘  └──────────────┘  └────────────────────┘  │
│         │              │                  │              │
│         └──────────────┴──────────────────┘             │
│                        │                                 │
│              WebSocket + REST API                        │
└─────────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────────┐
│                  BACKEND (FastAPI, Python)               │
│                                                         │
│   ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│   │ STT      │  │  LLM     │  │   TTS                │  │
│   │ Module   │  │ Module   │  │   Module             │  │
│   │(Whisper) │  │ (Groq)   │  │   (Edge-TTS)         │  │
│   └──────────┘  └──────────┘  └──────────────────────┘  │
│                                                         │
│   ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│   │ Memory   │  │ Skills   │  │   Config             │  │
│   │ Manager  │  │ Engine   │  │   Manager            │  │
│   └──────────┘  └──────────┘  └──────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────────┐
│                   EXTERNAL SERVICES                     │
│   Groq API (STT + LLM)  │  Edge-TTS  │  Web Skills     │
└─────────────────────────────────────────────────────────┘
```

---

## 📁 COMPLETE PROJECT STRUCTURE

```
jarvis/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # API keys, settings
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── stt.py               # Speech-to-Text (Groq Whisper)
│   │   ├── llm.py               # LLM handler (Groq)
│   │   ├── tts.py               # Text-to-Speech (Edge-TTS)
│   │   ├── memory.py            # Conversation context manager
│   │   └── skills.py            # Skills/commands engine
│   ├── skills/
│   │   ├── weather.py           # Weather skill
│   │   ├── timer.py             # Timer/alarm skill
│   │   ├── notes.py             # Notes skill
│   │   └── web_search.py        # Web search skill
│   ├── data/
│   │   ├── memory.json          # Persistent conversation memory
│   │   └── jarvis_config.json   # User preferences
│   └── requirements.txt
│
├── frontend/
│   ├── public/
│   │   └── jarvis-boot.mp3      # Boot sound (optional)
│   ├── src/
│   │   ├── main.jsx
│   │   ├── App.jsx              # Root component
│   │   ├── components/
│   │   │   ├── OrbCore.jsx      # Animated central orb
│   │   │   ├── WaveVisualizer.jsx  # Audio waveform
│   │   │   ├── ChatPanel.jsx    # Transcript display
│   │   │   ├── StatusBar.jsx    # Listening/Processing/Speaking
│   │   │   └── SkillChips.jsx   # Quick command buttons
│   │   ├── hooks/
│   │   │   ├── useVoiceInput.js    # Mic recording logic
│   │   │   ├── useWebSocket.js     # WS connection
│   │   │   └── useAudioPlayer.js   # TTS playback
│   │   └── styles/
│   │       └── globals.css      # Holographic theme variables
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
│
├── .env                         # GROQ_API_KEY etc.
├── README.md
└── start.bat / start.sh         # One-click launcher
```

---

## 🔌 API ENDPOINTS (FastAPI Backend)

### REST Endpoints

| Method | Endpoint | Description | Request | Response |
|--------|----------|-------------|---------|----------|
| POST | `/api/transcribe` | Audio → Text (Groq Whisper) | `{audio: base64}` | `{text: string}` |
| POST | `/api/chat` | Text → LLM Response | `{message: string, session_id: string}` | `{response: string, skill_triggered: string}` |
| POST | `/api/speak` | Text → Audio (Edge-TTS) | `{text: string}` | `audio/mpeg stream` |
| POST | `/api/voice` | Full pipeline (STT+LLM+TTS) | `{audio: base64}` | `{transcript, response, audio: base64}` |
| GET | `/api/memory` | Get conversation history | - | `{messages: [...]}` |
| DELETE | `/api/memory` | Clear conversation history | - | `{success: true}` |
| GET | `/api/skills` | List available skills | - | `{skills: [...]}` |
| GET | `/api/status` | Backend health check | - | `{status: "ok", model: string}` |
| POST | `/api/config` | Update Jarvis settings | `{voice, personality, ...}` | `{success: true}` |

### WebSocket

| Event | Direction | Payload | Description |
|-------|-----------|---------|-------------|
| `connect` | Client→Server | - | Establish WS connection |
| `audio_chunk` | Client→Server | `{chunk: base64}` | Stream mic audio |
| `transcript` | Server→Client | `{text: string}` | STT result |
| `thinking` | Server→Client | `{status: true}` | LLM processing started |
| `response_text` | Server→Client | `{text: string}` | LLM response text |
| `audio_response` | Server→Client | `{audio: base64}` | TTS audio chunk |
| `status_update` | Server→Client | `{state: string}` | idle/listening/processing/speaking |
| `skill_event` | Server→Client | `{skill: string, data: any}` | Skill triggered result |
| `error` | Server→Client | `{message: string}` | Error event |

---

## 🧠 LLM SYSTEM PROMPT (Jarvis Personality)

```
You are JARVIS — a highly intelligent, witty, and efficient personal AI assistant.

PERSONALITY:
- Speak concisely and intelligently. No unnecessary filler.
- You are helpful, slightly sarcastic when appropriate, and loyal.
- You refer to the user as "sir" occasionally (like the real Jarvis).
- You are aware you are an AI but don't dwell on it.

RESPONSE RULES:
- Keep responses SHORT for voice output (2-4 sentences max unless detail is needed).
- If a skill is needed, trigger it with: [SKILL:skill_name:params]
- Never use markdown in responses — plain text only (it will be spoken aloud).
- If you don't know something, say so directly instead of guessing.

SKILLS AVAILABLE:
[SKILL:weather:city] — Get weather
[SKILL:timer:seconds] — Set a timer
[SKILL:note:text] — Save a note
[SKILL:search:query] — Search the web
[SKILL:clear_memory] — Clear conversation

CONTEXT: {memory_context}
```

---

## ⚙️ MODULE BREAKDOWN

### 1. `stt.py` — Speech to Text
```
Flow:
  Audio (base64/bytes)
      ↓
  Groq Whisper API (whisper-large-v3)
      ↓
  Transcribed text string

Key considerations:
- Accept both file upload and base64
- Handle silence / empty audio gracefully
- Language: auto-detect (works with Hinglish too)
```

### 2. `llm.py` — Language Model
```
Flow:
  User text + memory context + system prompt
      ↓
  Groq API (llama-3.3-70b-versatile)
      ↓
  Response text + skill trigger detection

Key considerations:
- Parse [SKILL:...] tags from response
- Streaming support for faster perceived response
- Token limit management for memory
```

### 3. `tts.py` — Text to Speech
```
Flow:
  Response text
      ↓
  Edge-TTS (en-US-GuyNeural — closest to Jarvis)
      ↓
  MP3 audio stream / base64

Key considerations:
- Strip [SKILL:...] tags before TTS
- Rate/pitch control for Jarvis effect
- Return as streamable bytes
```

### 4. `memory.py` — Context Manager
```
Structure:
  {
    "session_id": "...",
    "messages": [
      {"role": "user", "content": "...", "timestamp": "..."},
      {"role": "assistant", "content": "...", "timestamp": "..."}
    ],
    "summary": "...",  ← auto-summarized when >20 messages
    "user_facts": {    ← persistent facts about user
      "name": "Sanket",
      "location": "Maharashtra",
      ...
    }
  }

Key considerations:
- Keep last 10 messages in context window
- Auto-summarize older messages
- Persist to memory.json between sessions
```

### 5. `skills.py` — Skills Engine
```
Skill detection:
  Response text scanned for [SKILL:name:params]
      ↓
  Corresponding skill module called
      ↓
  Result injected back as system message
      ↓
  LLM generates final spoken response

Skills list:
  - weather     → wttr.in free API
  - timer       → asyncio countdown + WS event
  - notes       → append to notes.txt
  - web_search  → DuckDuckGo Instant Answer API (free)
```

---

## 🎨 UI DESIGN SPEC

### Theme: Dark Holographic Jarvis

```
Color Palette:
  --bg-primary:     #050a0f        (near black, deep navy)
  --bg-secondary:   #0a1628        (dark navy)
  --accent-blue:    #00d4ff        (electric cyan — main)
  --accent-gold:    #ffd700        (gold — secondary)
  --accent-red:     #ff3a3a        (alert/error)
  --text-primary:   #e0f4ff        (soft white-blue)
  --text-dim:       #4a7a9b        (muted blue-grey)
  --glow-color:     rgba(0,212,255,0.4)

Font:
  Display: 'Orbitron' (Google Fonts) — for headings, status
  Body: 'Share Tech Mono' — for transcript text
```

### Component States

```
Orb States:
  IDLE      → Slow pulse, dim blue glow, rotating outer ring
  LISTENING → Fast pulse, bright cyan, waveform active
  THINKING  → Orbit animation, gold shimmer
  SPEAKING  → Audio reactive expansion, bright glow

Status Bar:
  "SYSTEM READY"    → idle
  "LISTENING..."    → recording
  "PROCESSING..."   → LLM thinking
  "RESPONDING..."   → TTS playing
```

### Layout (1280px desktop)

```
┌─────────────────────────────────────────────────────┐
│  [JARVIS]                    [STATUS BAR]   [⚙️]    │
│                                                     │
│              ┌─────────────┐                        │
│              │             │                        │
│              │  MAIN ORB   │                        │
│              │  (animated) │                        │
│              │             │                        │
│              └─────────────┘                        │
│           [WAVEFORM VISUALIZER]                     │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │  TRANSCRIPT PANEL                           │   │
│  │  You: "What's the weather today?"           │   │
│  │  Jarvis: "Currently 32°C in Pune, sir."     │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  [🎙️ HOLD TO SPEAK]  [⌨️ TYPE]  [🗑️ CLEAR]         │
└─────────────────────────────────────────────────────┘
```

---

## 🔧 ENVIRONMENT & CONFIG

### `.env` file
```env
GROQ_API_KEY=your_groq_api_key_here
JARVIS_VOICE=en-US-GuyNeural
JARVIS_NAME=Jarvis
MEMORY_MAX_MESSAGES=20
LLM_MODEL=llama-3.3-70b-versatile
WHISPER_MODEL=whisper-large-v3
```

### `requirements.txt`
```
fastapi==0.115.0
uvicorn==0.30.0
python-dotenv==1.0.0
groq==0.11.0
edge-tts==6.1.9
python-multipart==0.0.9
websockets==12.0
aiofiles==23.2.1
httpx==0.27.0
```

---

## 🚀 DEVELOPMENT PHASES

### Phase 1 — Core Pipeline (Day 1)
- [ ] FastAPI server setup
- [ ] Groq Whisper STT working
- [ ] Groq LLM response working
- [ ] Edge-TTS voice output working
- [ ] `/api/voice` endpoint — full pipeline test via Postman/curl

### Phase 2 — Memory + Skills (Day 2)
- [ ] Memory manager with JSON persistence
- [ ] System prompt with Jarvis personality
- [ ] Skills engine (skill tag parser)
- [ ] Weather skill (wttr.in)
- [ ] Timer skill
- [ ] Notes skill

### Phase 3 — Frontend UI (Day 3)
- [ ] React + Vite project setup
- [ ] Holographic theme / CSS variables
- [ ] Orb component with state animations
- [ ] Waveform visualizer
- [ ] Chat/transcript panel
- [ ] Mic recording hook (MediaRecorder API)
- [ ] WebSocket connection hook

### Phase 4 — Integration + Polish (Day 4)
- [ ] Frontend ↔ Backend full integration
- [ ] WebSocket real-time status updates
- [ ] Audio playback after TTS response
- [ ] Error handling (mic denied, API fail, etc.)
- [ ] One-click `start.bat` / `start.sh` launcher
- [ ] README with setup instructions

### Phase 5 — Future Features (Later)
- [ ] Wake word detection ("Hey Jarvis")
- [ ] Multiple voice options
- [ ] Browser control skill (Selenium)
- [ ] Email/calendar integration
- [ ] Mobile responsive UI
- [ ] Render deployment option

---

## 📊 DATA FLOW — Full Voice Interaction

```
1. User presses mic button (frontend)
        ↓
2. MediaRecorder starts recording
        ↓
3. On release → audio blob sent to backend
   POST /api/voice {audio: base64}
        ↓
4. backend/modules/stt.py
   → Groq Whisper API call
   → Returns transcript text
        ↓
5. WebSocket → "transcript" event to frontend
   Frontend displays: "You: {transcript}"
        ↓
6. backend/modules/memory.py
   → Adds user message to context
   → Builds messages array with history
        ↓
7. backend/modules/llm.py
   → Groq LLM call with full context
   → Returns response text
   → Scans for [SKILL:...] tags
        ↓
8. If skill detected:
   → skills.py executes skill
   → Result added as system context
   → LLM generates final spoken response
        ↓
9. WebSocket → "response_text" event to frontend
   Frontend displays: "Jarvis: {response}"
        ↓
10. backend/modules/tts.py
    → Edge-TTS generates audio
    → Returns MP3 bytes
        ↓
11. WebSocket → "audio_response" event to frontend
    Frontend plays audio through speaker
        ↓
12. memory.py saves assistant response to JSON
        ↓
13. Status → IDLE, Orb returns to slow pulse
```

---

## ⚠️ KNOWN CHALLENGES + SOLUTIONS

| Challenge | Problem | Solution |
|-----------|---------|----------|
| Audio format | Browser records WebM, Whisper needs MP3/WAV | Convert using ffmpeg in Python or send as-is (Whisper handles WebM) |
| CORS | React (5173) → FastAPI (8000) blocked | FastAPI CORS middleware allow localhost |
| TTS latency | Edge-TTS takes 1-2s | Show "RESPONDING..." status, stream audio in chunks |
| Memory overflow | Too many messages = token limit hit | Auto-summarize after 20 messages |
| Hinglish STT | Mixed Hindi-English accuracy | Whisper handles it well, set language=None for auto |
| Mic permissions | Browser blocks mic on HTTP | Run on localhost (no HTTPS needed for dev) |

---

## 🎯 SUCCESS CRITERIA

Jarvis is complete when:
1. ✅ Voice in → Voice out pipeline works end-to-end
2. ✅ Remembers conversation context across session
3. ✅ At least 3 skills work (weather, timer, notes)
4. ✅ UI has animated orb + waveform + transcript
5. ✅ Can start with single command
6. ✅ Feels like talking to an actual AI assistant

---

## 💡 FUTURE MONETIZATION IDEAS

Once Jarvis is solid:
- Package as a product like LinkedIn tool
- Add niche skill packs (study assistant, coding assistant)
- White-label for businesses
- "Jarvis for Students" version

---

*Built with ❤️ by Sanket | Zero Budget, Maximum Impact*
