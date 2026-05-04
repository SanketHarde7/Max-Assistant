# JARVIS v4.0 — Sanket's AI Assistant

**Bhai, ye bilkul FREE hai. Koi subscription nahi, koi API charges nahi.**

## What's New in v4.0

- **Friendly Tone** — No "sir" overload. Bhai/yaar style. Hinglish mix.
- **Email Integration** — Gmail via SMTP/IMAP (App Password). Send & check emails.
- **Calendar** — Local JSON calendar. Zero cloud, zero API.
- **Browser Automation** — Selenium-based. Scrape, click, type, open URLs.
- **Smart Home (IR Blaster)** — Havells fan, TV, AC control via Broadlink RM Mini 3 / Pro.
- **Plugin System** — Drop `.py` files in `plugins/` folder, auto-load.
- **PC Full Control** — Brightness, clipboard, lock PC, volume, apps, shutdown.
- **Personality Evolution** — Auto-learns user preferences, facts, interaction style.
- **Screen Vision** — Screenshot + Vision model to read screen content.
- **Code Engine** — Write, run, review, fix code in 10+ languages.
- **File Manager** — Search, read, edit, list files across workspace.

---

## Setup

### 1. Clone / Copy Files

```bash
cd jarvis-backend/
```

### 2. Create Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate     # Windows
source venv/bin/activate # Linux/Mac
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Create `.env` File

```env
# ── Required ──
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ── Optional: Email ──
EMAIL_ADDRESS=your.email@gmail.com
EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   # Gmail App Password, NOT your Gmail password

# ── Optional: Smart Home (IR Blaster) ──
IR_BLASTER_ENABLED=true
IR_BLASTER_IP=192.168.1.45          # Your Broadlink RM Mini 3 IP
IR_BLASTER_TYPE=broadlink

# ── Optional: Tuya WiFi devices ──
TUYA_DEVICE_ID=
TUYA_LOCAL_KEY=
TUYA_DEVICE_IP=

# ── Optional: Custom paths ──
WORKSPACE_DIR=C:\Users\Sanket\projects
SEARCH_DIRS=C:\Users\Sanket\Desktop,C:\Users\Sanket\Documents
```

### 5. Run

```bash
python main.py
```

Server starts at `http://localhost:8000`

---

## Havells Fan IR Control Setup

Tera fan remote se chalta hai (mobile nahi). **Solution: IR Blaster**

### Hardware Needed
- **Broadlink RM Mini 3** (~₹800-1200 on Amazon/Flipkart)
- Or **Broadlink RM4 Pro** (supports RF + IR)

### Setup Steps

1. **Connect Broadlink** to your WiFi via "Broadlink" app.
2. **Find IP** of Broadlink device (router admin page ya Fing app).
3. **Add IP to `.env`**:
   ```env
   IR_BLASTER_ENABLED=true
   IR_BLASTER_IP=192.168.1.45
   ```
4. **Learn Commands** — First time setup:
   ```bash
   # Use Broadlink app to learn commands, OR
   # Use JARVIS: "fan command learn karo"
   # It will capture IR signals from your Havells remote
   ```

### Supported Commands
- `fan on` / `fan off`
- `fan speed1` to `fan speed5`
- `fan swing`
- `fan timer`

---

## Plugin System

Drop any `.py` file in `plugins/` folder:

```python
# plugins/my_plugin.py

def register():
    return {
        "skill_name": "my_skill",
        "description": "Does something cool",
        "handler": lambda *args: f"Result: {args}"
    }
```

JARVIS auto-loads on startup. Say `plugin reload` or hit `/api/plugins/reload`.

---

## API Endpoints

| Category | Endpoint | Method |
|----------|----------|--------|
| Chat | `/ws` | WebSocket |
| Chat | `/api/chat` | POST |
| Health | `/health` | GET |
| TTS | `/api/speak` | POST |
| STT | `/api/listen` | POST |
| Files | `/api/files/search` | GET |
| Files | `/api/files/list` | GET |
| Files | `/api/files/read` | GET |
| Screen | `/api/screenshot` | POST |
| Screen | `/api/screen/read` | POST |
| PC Control | `/api/volume` | POST |
| PC Control | `/api/open-app` | POST |
| PC Control | `/api/open-url` | POST |
| PC Control | `/api/type-text` | POST |
| PC Control | `/api/pc/brightness` | POST |
| PC Control | `/api/pc/clipboard` | POST |
| PC Control | `/api/pc/lock` | POST |
| PC Control | `/api/shutdown` | POST |
| PC Control | `/api/restart` | POST |
| Code | `/api/generate-code` | POST |
| Code | `/api/run-code` | POST |
| Code | `/api/review-code` | POST |
| Code | `/api/fix-code` | POST |
| Code | `/api/project-scaffold` | POST |
| Email | `/api/email/send` | POST |
| Email | `/api/email/check` | GET |
| Calendar | `/api/calendar/today` | GET |
| Calendar | `/api/calendar/week` | GET |
| Calendar | `/api/calendar/add` | POST |
| Browser | `/api/browser/open` | POST |
| Browser | `/api/browser/click` | POST |
| Browser | `/api/browser/type` | POST |
| Browser | `/api/browser/scrape` | POST |
| Smart Home | `/api/smarthome/fan` | POST |
| Smart Home | `/api/smarthome/light` | POST |
| Smart Home | `/api/smarthome/ac` | POST |
| Plugins | `/api/plugins/list` | GET |
| Plugins | `/api/plugins/reload` | POST |

---

## Voice Commands You Can Try

- `"Email check karo"` → `[SKILL:email_check]`
- `"Calendar mein meeting add karo"` → `[SKILL:calendar_add:Meeting:2026-05-04:15:00]`
- `"Fan band karo"` → `[SKILL:fan:off]`
- `"Brightness kam karo"` → `[SKILL:brightness:down:10]`
- `"Clipboard mein kya hai"` → `[SKILL:clipboard:get]`
- `"System lock karo"` → `[SKILL:lock_pc]`
- `"Flipkart pe iPhone price check karo"` → `[SKILL:browser_scrape:flipkart.com:iphone 16 price]`
- `"WhatsApp kholo"` → `[SKILL:open_app:whatsapp]`

---

## Architecture

```
jarvis-backend/
├── main.py              # FastAPI server + all endpoints
├── config.py            # Settings, .env loader
├── agent_core.py        # Orchestrator (LLM + Skills + Memory)
├── requirements.txt
├── modules/
│   ├── llm.py           # Groq LLM + Vision + Friendly prompts
│   ├── skills.py        # 30+ skills registry
│   ├── memory.py        # Conversation + Facts + Personality
│   ├── code_engine.py   # Code gen, run, review, fix
│   ├── file_manager.py  # File search, read, edit, list
│   ├── stt.py           # Whisper speech-to-text
│   ├── tts.py           # Edge-TTS text-to-speech
│   ├── email_agent.py   # Gmail SMTP/IMAP
│   ├── calendar_agent.py# Local JSON calendar
│   ├── browser_agent.py # Selenium automation
│   ├── smarthome_agent.py# IR + Tuya smart home
│   └── plugin_loader.py # Dynamic plugin system
└── plugins/             # Drop custom plugins here
```

---

**Made with bhai-chara. No sir, just code.**
