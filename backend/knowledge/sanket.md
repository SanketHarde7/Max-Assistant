# Sanket's Projects & Context

## About Me

- Name: Sanket
- College: PVP College Loni, Maharashtra — B.Sc. Computer Science, Semester IV (Pune University)
- Role: Indie developer / founder, building and selling software on zero budget
- Location: Loni, Ahilyanagar district, Maharashtra

---

## Project 1 — ClientDesk CRM

**What it is:** A CRM tool built for freelancers.

**Tech stack:** Node.js + Express + MongoDB + Vanilla JS

**Pricing:** ₹99/year

**Live URL:** clientdesk2.onrender.com

**Key features:**
- Client management and invoice tracking
- AI-powered payment reminder emails (Groq)
- Campaign scheduling
- PWA support (installable on mobile)
- Groq AI chat widget
- jsPDF invoice downloads
- Three-part onboarding flow
- Backend analytics via MongoDB aggregation pipelines

**Status:** Listed on Acquire.com at $5k asking price, $0 revenue currently.

**Target audience:** US freelancers

**Marketing copy rules:**
- English only
- No long dashes
- Always mention AI payment reminder
- Price shown as ₹99/year

---

## Project 2 — LinkedIn Automation Tool

**What it is:** Python bot that automates LinkedIn connection requests and commenting.

**Tech stack:** Python + Selenium + Groq (llama-3.3-70b-versatile)

**Architecture:**
- Local agent: buyer's PC runs the Selenium bot
- Frontend dashboard: React + Vite (hosted on Render free tier)
- Backend API: Flask-SocketIO (hosted on Render free tier)
- Split architecture reason: Render's 512MB RAM limit kills Selenium

**Two modes:**
1. Profile Search mode — sends connection requests with personalized AI notes
2. Feed Monitor mode — generates contextual AI comments on posts

**Key fixes applied:**
- Chrome flags for headless Render deployment
- `Keys.CONTROL + Keys.RETURN` for LinkedIn comment submission
- Multi-keyword search fix
- Duplicate post ID bug fixed (MD5 hash of text+author)
- Optimistic UI state in BotControl.tsx
- WebSocket polling fallback

**Setup wizard:** `setup_wizard.py` — buyers configure their own niche, Groq auto-generates keyword categories from product description

**UI:** Dark Tkinter GUI + holographic landing page

**Pending:** Chrome session save fix, comment submit final test

---

## Project 3 — MAX (AI Assistant)

**What it is:** Personal AI voice assistant — this system you're talking to right now.

**Tech stack:** FastAPI + Groq (Whisper STT + LLaMA LLM) + Edge-TTS

**Frontend:** React + Vite + Three.js (3D orb)

**Key modules:**
- agent_core.py — orchestrator
- skills.py — 30+ skills
- memory.py — persistent conversation memory
- gatekeeper.py — response quality filter
- knowledge_base.py — ChromaDB RAG system
- app_indexer.py — scans all installed apps on Windows

**Features:**
- Voice input (Groq Whisper STT)
- TTS output (Edge-TTS, Indian English voice)
- App opening (4-step chain: protocol → direct exe → app indexer → shell)
- System info (CPU, RAM, disk, battery via psutil)
- Media control (play/pause/next via media keys)
- Reminders (persistent, desktop notifications)
- Knowledge base (ChromaDB + sentence-transformers, this file!)
- Email (Gmail SMTP/IMAP)
- Calendar (local JSON)
- Browser automation (Selenium)
- Smart home (IR Blaster via Broadlink)
- Code engine (write, run, review, fix in 10+ languages)
- File manager (search, read, edit)
- Screen reader (Groq Vision model)

---

## Current Semester — Exam Topics

**MTC-241 Computational Geometry (Sem IV):**
- 2D/3D transformations (translation, rotation, scaling, shearing)
- Homogeneous coordinates
- Projections (orthographic, perspective, oblique)
- Bézier curves (de Casteljau algorithm)
- B-splines

**DBMS:**
- Concurrency control (2PL, timestamp ordering)
- Recovery (ARIES, WAL)
- PL/pgSQL

---

## Development Philosophy

- Zero budget constraint — all tools must be free
- Surgical targeted fixes over full rewrites
- Pushes back when diagnosis steps are skipped before implementation
- Favors working examples and visual aids when learning
- Comfortable with Linear Algebra and matrix operations

---

## Tech Preferences

- **Languages:** Python (primary), JavaScript/React
- **AI:** Groq API (free tier), LLaMA models
- **DB:** MongoDB, SQLite, JSON files
- **Deploy:** Render free tier
- **Editor:** VS Code

---

## GitHub Copilot Setup

File: `.github/copilot-instructions.md`
Covers: Python + JavaScript stack, document parsing, multi-file context, error handling, speed optimization using `context.md` and `#file` tags.