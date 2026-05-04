# JARVIS Advanced Features Roadmap
## Sanket ke liye — Zero Budget, Maximum Impact

---

## ✅ ALREADY WORKING (current code mein)
- Screen Reader (Vision model via Groq)
- Multi-Modal image analysis
- Long-term memory (JSON + permanent_rules.json)
- Wake word detection (speech_recognition, Google STT)

---

## 🔧 FEATURE IMPLEMENTATION PLAN

---

### 1. Wake Word — "Hey Jarvis"
**Status:** Basic version done (stt.py). Upgrade option:

**Option A — Free (current):**
```python
# speech_recognition + Google STT
# Works but needs internet, ~1s delay
pip install SpeechRecognition pyaudio
```

**Option B — pvporcupine (offline, instant):**
```python
# Picovoice free tier: 1 wake word, offline, <10ms latency
pip install pvporcupine
# Get free key: console.picovoice.ai
```
**Recommendation:** Start with Option A (already done). pvporcupine upgrade agar delay bothers kare.

---

### 2. Browser Automation (Selenium)
**New file: `modules/browser_agent.py`**

```python
# Skills to add:
[SKILL:browser_open:url]          — Open URL in controlled Chrome
[SKILL:browser_click:selector]    — Click element
[SKILL:browser_type:selector:text]— Type in input field
[SKILL:browser_scrape:url:query]  — Scrape specific info from page
[SKILL:browser_screenshot]        — Screenshot of browser

# Use cases:
# "Flipkart pe iPhone price check karo"
# "LinkedIn pe mera profile kholo"
# "Form fill karo meri details se"
```

**Zero cost stack:**
```
pip install selenium webdriver-manager
# webdriver-manager auto-downloads ChromeDriver — no manual setup
```

---

### 3. Email Integration
**New file: `modules/email_agent.py`**

```python
# Skills to add:
[SKILL:email_send:to:subject:body]  — Send email
[SKILL:email_check]                 — Check last 5 unread emails
[SKILL:email_reply:message_id:body] — Reply to email

# .env additions:
EMAIL_ADDRESS=sanket@gmail.com
EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx  # Gmail App Password (not real password)
IMAP_SERVER=imap.gmail.com
SMTP_SERVER=smtp.gmail.com

# Zero cost — Gmail free tier
# Need to enable "App Passwords" in Google Account
```

---

### 4. Calendar Integration
**New file: `modules/calendar_agent.py`**

```python
# Skills to add:
[SKILL:calendar_today]              — What's today's schedule
[SKILL:calendar_add:title:date:time]— Add event
[SKILL:calendar_week]               — This week's events

# Two approaches:
# Option A: Google Calendar API (free tier, needs setup)
# Option B: local .ics file (zero setup, offline)

# Recommendation: Start with local .ics, Google Calendar later
pip install icalendar arrow
```

---

### 5. Smart Home Control
**New file: `modules/smarthome_agent.py`**

```python
# Depends on devices:

# Option A: WiFi devices (Tuya/Smart Life ecosystem) — most common in India
pip install tinytuya
[SKILL:smart_light:on|off|dim:50]
[SKILL:smart_ac:on|off|temp:24]

# Option B: Home Assistant (if already set up)
# REST API calls to local HA instance

# Option C: IR Blaster (broadlink) — controls any IR device
pip install broadlink
```

**Recommendation:** Tell me which devices you have — plan accordingly.

---

### 6. Screen Reader — ✅ DONE
Already working via `[SKILL:read_screen:window]` using Groq Vision.

**Enhancement ideas:**
- Auto-read when user asks about "kya hai screen pe"
- Watch mode — periodic screen monitoring

---

### 7. Multi-Modal — ✅ DONE
`analyze_image_with_prompt()` in llm.py working.

**Enhancement: Voice + Image combined:**
```python
# User sends image via chat + voice query
# "Is image mein kya hai" + image upload
# Frontend sends image as base64 + audio
# Backend: STT for voice + Vision for image → combined response
```

---

### 8. Long-Term Memory — ✅ DONE
memory.json + permanent_rules.json working.

**Enhancement — User Fact Learning:**
```python
# Auto-detect and store facts from conversation:
# "Mera naam Sanket hai" → user_facts["name"] = "Sanket"
# "Main Pune mein rehta hoon" → user_facts["city"] = "Pune"
# "Mujhe Python pasand hai" → user_facts["fav_language"] = "Python"

# Add to llm.py — after each response, run fact extraction:
async def extract_and_store_facts(user_text: str, memory_manager):
    ...
```

---

### 9. Personality Evolution
**Status:** Partially done via memory context injection.

**Full implementation:**
```python
# Track interaction patterns:
# - User prefers short answers → reduce max_tokens
# - User asks mostly coding → increase code skill priority
# - User's communication style → adapt tone
# - Time of day → greeting style changes (already done)

# Add to memory.json:
"personality_profile": {
    "prefers_short_answers": true,
    "main_domain": "coding",
    "language_mix": 0.7,  # 0=pure Hindi, 1=pure English
    "humor_level": "medium"
}
```

---

### 10. Plugin System
**New file: `modules/plugin_loader.py`**

```python
# Simple dynamic import system:
# 1. Create jarvis/plugins/ folder
# 2. Each plugin = one Python file with register() function
# 3. On startup, auto-load all plugins
# 4. Skills auto-register

# Example plugin: plugins/cricket_score.py
def register():
    return {
        "skill_name": "cricket_score",
        "handler": get_cricket_score,
        "description": "Get live cricket score"
    }

async def get_cricket_score(team="India"):
    # fetch from cricbuzz or cricapi
    ...
```

---

## 🚀 RECOMMENDED IMPLEMENTATION ORDER

```
Week 1 (Abhi):
  ✅ Bug fixes (config, skills, llm) — done
  → Browser Automation (most useful, relatively simple)
  → Email Integration (high value)

Week 2:
  → Plugin System (unlocks everything else easily)
  → Calendar Integration
  → Long-term fact learning enhancement

Week 3:
  → Smart Home (depends on your devices)
  → pvporcupine wake word upgrade
  → Personality evolution

Future:
  → Multi-modal voice+image
  → Voice cloning for Jarvis sound
```

---

## 📦 requirements.txt ADDITIONS NEEDED

```txt
# Browser Automation
selenium>=4.18.1
webdriver-manager>=4.0.1

# Email
# (smtplib and imaplib are built-in Python — no install needed)

# Calendar
icalendar>=5.0.14
arrow>=1.3.0

# Wake Word (upgrade)
pvporcupine>=3.0.0   # needs free API key from picovoice.ai

# Smart Home
tinytuya>=1.13.1     # for Tuya/Smart Life devices
broadlink>=0.18.3    # for IR blaster devices

# Screen Automation
pygetwindow>=0.0.9   # for window targeting
```

---

*Bhai — yeh roadmap clear hai. Kaunsa feature pehle implement karna hai bol, direct code dunga.*
