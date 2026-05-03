# JARVIS Agent Architecture v3.0 — Next-Gen AI Assistant

## Core Philosophy
JARVIS is not a chatbot — it's an **agentic AI** that can:
- **Plan**: Break complex tasks into sub-tasks
- **Reason**: Multi-step reasoning with intermediate checks
- **Execute**: Actually DO things (write code, run it, manage files)
- **Learn**: Remember user preferences and corrections
- **Self-Correct**: Fix its own mistakes

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                                │
│         (Voice / Text / WebSocket / REST API)                        │
└─────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR AGENT                                │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐    │
│  │   Router     │ │   Planner    │ │   Executor               │    │
│  │  (Intent     │ │  (Task De-   │ │  (Multi-Step             │    │
│  │  Classifier) │ │  composition)│ │  Execution)              │    │
│  └──────────────┘ └──────────────┘ └──────────────────────────┘    │
│                                                                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐    │
│  │   Memory     │ │   Learner    │ │   Self-Corrector         │    │
│  │  (Context +  │ │  (User       │ │  (Retry Logic +          │    │
│  │  Facts)      │ │  Preferences)│ │  Error Recovery)         │    │
│  └──────────────┘ └──────────────┘ └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────────┐
│                    SKILL ECOSYSTEM                                   │
│                                                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  CODE SKILLS     │  │  FILE SKILLS     │  │  SYSTEM SKILLS   │  │
│  │  write_code      │  │  find_and_explain│  │  open_app        │  │
│  │  run_code        │  │  list_files      │  │  screenshot      │  │
│  │  code_review     │  │  read_file       │  │  volume          │  │
│  │  fix_code        │  │  edit_file       │  │  system_shutdown │  │
│  │  project_scaffold│  │  search_files    │  │  system_restart  │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
│                                                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  WEB SKILLS      │  │  PRODUCTIVITY    │  │  SMART SKILLS    │  │
│  │  search          │  │  timer           │  │  weather         │  │
│  │  youtube_search  │  │  note            │  │  clipboard       │  │
│  │  web_open        │  │  reminder        │  │  smart_search    │  │
│  │  whatsapp_message│  │  task_planner    │  │  git_operations  │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────────┐
│                    INFRASTRUCTURE                                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │
│  │ STT      │ │ LLM      │ │ TTS      │ │ Storage  │               │
│  │ Whisper  │ │ Groq     │ │ Edge-TTS │ │ JSON/FS  │               │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## New Skills (Agent Level)

### CODE SKILLS
| Skill | Trigger | What It Does |
|-------|---------|--------------|
| `write_code` | `[SKILL:write_code:lang:hint]` | Generates clean code via LLM, saves to file |
| `run_code` | `[SKILL:run_code:filepath]` | Executes code file, captures output/errors |
| `code_review` | `[SKILL:code_review:filepath]` | Analyzes code, finds bugs, suggests improvements |
| `fix_code` | `[SKILL:fix_code:filepath:issue]` | Reads code, fixes specific issue, saves |
| `project_scaffold` | `[SKILL:project_scaffold:type:name]` | Creates project skeleton (react, python, node) |

### FILE SKILLS
| Skill | Trigger | What It Does |
|-------|---------|--------------|
| `find_and_explain` | `[SKILL:find_and_explain:filename:context]` | Smart search → context filter → LLM explain |
| `list_files` | `[SKILL:list_files:folder]` | Lists folder contents with file sizes |
| `read_file` | `[SKILL:read_file:filepath]` | Reads file and returns content |
| `edit_file` | `[SKILL:edit_file:filepath:changes]` | Edits specific lines in a file |
| `search_files` | `[SKILL:search_files:query]` | Full-text search across workspace |

### PRODUCTIVITY SKILLS
| Skill | Trigger | What It Does |
|-------|---------|--------------|
| `reminder` | `[SKILL:reminder:time:task]` | Context-aware reminders |
| `task_planner` | `[SKILL:task_planner:goal]` | Breaks goal into actionable sub-tasks |
| `git_operations` | `[SKILL:git:command]` | Git commands (status, commit, push) |
| `clipboard` | `[SKILL:clipboard:action]` | Clipboard history manager |

---

## Agent Workflow: Multi-Step Task Execution

```
User: "Ek React app banao todo list wala"

Step 1: Intent Classification
→ Router detects: CODE + PROJECT_SCAFFOLD + WRITE_CODE

Step 2: Task Planning
→ Planner breaks into sub-tasks:
  1. Scaffold React project structure
  2. Write package.json with dependencies
  3. Write main App.jsx component
  4. Write TodoList component
  5. Write CSS styles
  6. Write README with run instructions

Step 3: Sequential Execution
→ Executor runs each step, checking for errors:
  ✓ Step 1: mkdir -p todo-app/{src,public,components}
  ✓ Step 2: Write package.json
  ✓ Step 3: Write App.jsx
  ...

Step 4: Verification
→ Auto-runs npm install check
→ Reports: "Todo app ready sir, 'npm start' se chalu karein"
```

---

## Code Skill Flow Detail

### write_code
```
User: "fibonacci series ka code likh"
        ↓
LLM: Intent = write_code
        ↓
[SKILL:write_code:python:fibonacci_series]
        ↓
CodeEngine:
  1. LLM call → "Generate clean Python fibonacci code"
  2. Language auto-detect (python from tag)
  3. Generate filename: fibonacci_series.py
  4. Save to: WORKSPACE_DIR/CODE_SAVE_DIR/fibonacci_series.py
  5. Return: file path + confirmation
        ↓
TTS: "Fibonacci series ka code likh diya sir, 
      fibonacci_series.py mein save ho gayi."
```

### find_and_explain
```
User: "linkedin automation project ki main.py samjha"
        ↓
[SKILL:find_and_explain:main.py:linkedin automation]
        ↓
FileManager:
  PASS 1 - SEARCH:
    1. Search WORKSPACE_DIR for main.py
    2. Find multiple: 
       /jarvis/backend/main.py
       /linkedin-automation/main.py  ← context match!
       /desktop/test/main.py
    3. Context "linkedin automation" → rank #2 highest
    4. Read file content
  
  PASS 2 - EXPLAIN:
    5. Send to LLM: "Explain this code in simple words..."
    6. Get explanation
        ↓
TTS: "Sir, yeh file ek FastAPI server hai.
      Ismein do routes hain — /login aur /scrape.
      Login route LinkedIn credentials se token banata hai..."
```

---

## Environment Variables

```env
# === API KEYS ===
GROQ_API_KEY=your_groq_api_key_here

# === PATHS (CRITICAL) ===
WORKSPACE_DIR=C:/Users/Sanket/projects
SEARCH_DIRS=C:/Users/Sanket/Desktop,C:/Users/Sanket/Documents,C:/Users/Sanket/projects
CODE_SAVE_DIR=C:/Users/Sanket/projects/jarvis-generated
MAX_FILE_SIZE_KB=5000

# === LLM ===
LLM_MODEL=llama-3.3-70b-versatile
WHISPER_MODEL=whisper-large-v3

# === TTS ===
TTS_VOICE=en-US-GuyNeural
TTS_RATE=+0%
TTS_PITCH=+0Hz

# === MEMORY ===
MEMORY_FILE=backend/data/memory.json
MEMORY_MAX_MESSAGES=20
MEMORY_SUMMARIZE_THRESHOLD=20

# === AGENT ===
AGENT_MAX_STEPS=10
AGENT_AUTO_CORRECT=true
AGENT_LEARN_PREFERENCES=true
```
