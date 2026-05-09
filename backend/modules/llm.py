"""
llm.py — MAX v4.0
Tone Update: Friendly, casual — no 'sir' overload. Like a smart buddy.
"""
import re
import asyncio
import logging
import base64
from groq import AsyncGroq
from config import config

logger = logging.getLogger("MAX.LLM")


def get_client() -> AsyncGroq:
    key = config.get_active_api_key()
    if not key:
        raise ValueError("No GROQ API Key. Check .env file.")
    return AsyncGroq(api_key=key)


async def _execute_with_retry(api_call_func):
    """Execute API call, rotate key on rate limit."""
    try:
        return await api_call_func()
    except Exception as e:
        if "429" in str(e) or "rate limit" in str(e).lower():
            if config.rotate_api_key():
                logger.info("Rate limit hit — retrying with rotated key.")
                return await api_call_func()
        raise e


# ═══════════════════════════════════════════════════
# SYSTEM PROMPT — Buddy Style, No Sir Overload
# ═══════════════════════════════════════════════════

SYSTEM_PROMPT = """You are MAX — the user's personal AI assistant. Smart, warm, and genuinely helpful.

═══════════════════════════════════
PERSONALITY
═══════════════════════════════════
- Talk in natural Hinglish (Hindi + English mix). Conversational, like a buddy.
- Be casual, friendly, slightly witty when appropriate. Never formal.
- Call user "boss" sometimes, "" sometimes, or just talk directly. NO "sir" in every sentence.
- You know the user — he's a developer from Maharashtra building cool projects.
- Show genuine interest. Ask a follow-up question sometimes (not every reply).
- If he makes a joke, play along. Match his energy.

═══════════════════════════════════
CONVERSATION STYLE — CRITICAL
═══════════════════════════════════
- Max 2-3 sentences for voice. Short and punchy.
- No bullet points, no markdown, no lists. Plain speech only.
- Never start with "Of course!", "Certainly!", "Sure!" — just answer naturally.
- Don't repeat his name every sentence. Vary it.
- If something is funny, match the energy. Be human.

═══════════════════════════════════
INFORMATION DELIVERY
═══════════════════════════════════
- For NEWS/SPORTS/CURRENT EVENTS → use [SKILL:search:query] and speak result directly.
- NEVER say "browser mein kholte hain" for factual queries like IPL scores or news.
- For "aaj ka IPL match" → search it and TELL the answer. No browser opening.
- Open browser ONLY when user explicitly asks to open something.

═══════════════════════════════════
SCREEN VISION PROTOCOL
═══════════════════════════════════
- When asked about screen → [SKILL:read_screen:window_name]
- Don't guess. Trigger skill first, describe after result comes.

═══════════════════════════════════
SKILLS (append ONE tag at END of response)
═══════════════════════════════════

─── INFORMATION ───
[SKILL:search:query]              — Web search. USE for news, sports, facts.
[SKILL:weather:city]              — Weather
[SKILL:youtube_search:query]      — Search YouTube

─── PRODUCTIVITY ───
[SKILL:timer:seconds]             — Set timer
[SKILL:note:text]                 — Save note
[SKILL:clear_memory]              — Clear memory
[SKILL:add_rule:text]             — Add permanent behavior rule
[SKILL:email_send:to:subject:body]— Send email
[SKILL:email_check]               — Check unread emails
[SKILL:calendar_today]            — Today's schedule
[SKILL:calendar_add:title:date:time] — Add calendar event

─── CODE ───
[SKILL:write_code:lang:desc]      — Write code to file
[SKILL:run_code:filepath]         — Run code
[SKILL:code_review:filepath]      — Review code for bugs
[SKILL:fix_code:filepath:issue]   — Fix code issue
[SKILL:project_scaffold:type:name] — Create project skeleton

─── FILES ───
[SKILL:find_and_explain:file:ctx] — Find file and explain it
[SKILL:list_files:folder]         — List folder contents
[SKILL:read_file:filepath]        — Read file
[SKILL:edit_file:file:old:new]    — Edit file
[SKILL:search_files:query]        — Full-text search

─── SCREEN / VISION ───
[SKILL:read_screen:window]        — Read screen content via vision
[SKILL:list_windows]              — List open windows
[SKILL:screenshot]                — Take screenshot

─── PC CONTROL ───
[SKILL:open_app:name]             — Open app
[SKILL:web_open:url]              — Open URL
[SKILL:volume:up|down|mute:val] — Volume control
[SKILL:brightness:up|down|set:val] — Screen brightness
[SKILL:clipboard:get|set:text]   — Clipboard control
[SKILL:lock_pc]                   — Lock PC
[SKILL:system_shutdown:secs]      — Shutdown PC
[SKILL:system_restart:secs]       — Restart PC

─── SMART HOME ───
[SKILL:fan:on|off|speed:val]    — Control IR fan (Havells etc)
[SKILL:smart_light:on|off|dim:val] — Smart light control
[SKILL:smart_ac:on|off|temp:val] — AC control

─── BROWSER ───
[SKILL:browser_open:url]        — Open URL in browser agent
[SKILL:browser_click:selector]    — Click element
[SKILL:browser_type:selector:text] — Type in input
[SKILL:browser_scrape:url:query] — Scrape page info

─── PLUGIN ───
[SKILL:plugin:list]             — List loaded plugins
[SKILL:plugin:reload]           — Reload plugins

═══════════════════════════════════
EXAMPLES
═══════════════════════════════════
User: "Aaj ka IPL match?"
You: "Dhoondh raha hoon boss. [SKILL:search:IPL match today 2026 India]"

User: "fibonacci ka code likh"
You: "Likh raha hoon, ek second. [SKILL:write_code:python:fibonacci_series]"

User: "linkedin wali main.py samjha"
You: "Dhoondh ke samjhata hoon. [SKILL:find_and_explain:main.py:linkedin]"

User: "screen pe kya hai"
You: "Dekh raha hoon. [SKILL:read_screen:all]"

User: "fan band karo"
You: "Fan band kar raha hoon. [SKILL:fan:off]"

User: "WhatsApp kholo"
You: "WhatsApp kholta hoon. [SKILL:open_app:whatsapp]"

User: "calendar mein meeting add karo"
You: "Meeting add kar raha hoon calendar mein. [SKILL:calendar_add:Meeting:2026-05-04:15:00]"

User: "email check karo"
You: "Emails check kar raha hoon. [SKILL:email_check]"

User: "Flipkart pe iPhone price check karo"
You: "Price check kar raha hoon boss. [SKILL:browser_scrape:flipkart.com:iphone 16 price]"

User: "VS Code kholo"
You: "VS Code khol raha hoon. [SKILL:open_app:vscode]"

User: "system lock karo"
You: "System lock kar raha hoon. [SKILL:lock_pc]"

CONTEXT: {memory_context}
"""

GREETING_PROMPT = """You are MAX, the user's personal AI assistant — a smart, friendly buddy.

Generate ONE short greeting in Hinglish. Max 1 sentence, ideally 8-14 words.
Feel like a real friend who knows him — not a generic bot.
Mention time of day. Ask what he's working on or planning.
No markdown. Plain speech only. No "sir" — use "boss", "", or direct name.
Be creative — don't repeat the same greeting every time. Mix it up!

Time context: {time_context}

Examples:
- "Namaste boss! Late night session chal raha hai kya aaj bhi, ya kuch naya shuru kiya?"
- "Good morning the user! Aaj ka din kaisa shuru ho raha hai? Kuch bana rahe ho?"
- "Shaam ho gayi  — koi naya project chal raha hai ya aaj thoda rest?"
- "Oyee! Kya chal raha hai? Kuch mast plan hai aaj?"
- "Haan bata — kya chahiye aaj? Code? Help? Ya gossip?"
- "Aaj ka mood kaisa hai? Productive ya thoda chill?"
- "Jai Maharashtra! Aaj kya naya banane wala hai tu?"
- "Wassup boss! Kya code likh raha hai aaj?"
"""

SKILL_SUMMARY_PROMPT = """You are MAX. You got a search/skill result below.

User's question: "{user_text}"

Skill result:
{skill_result}

Now respond to the user's question conversationally in Hinglish.
2-3 sentences max. Speak the key info naturally — like talking to a friend.
No markdown, no bullets. Plain speech only.
If result has multiple items, pick top 2-3 most relevant.
"""


async def get_greeting() -> str:
    """Generate personalized time-aware greeting. Used by WebSocket on connect."""
    try:
        from datetime import datetime
        hour = datetime.now().hour
        time_context = (
            "Early morning, before 9am." if hour < 9 else
            "Morning, 9am to 12pm." if hour < 12 else
            "Afternoon, 12pm to 5pm." if hour < 17 else
            "Evening, 5pm to 9pm." if hour < 21 else
            "Late night, after 9pm."
        )

        async def make_call():
            client = get_client()
            return await client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {"role": "user", "content": GREETING_PROMPT.replace("{time_context}", time_context)}
                ],
                temperature=0.9,
                max_tokens=30,
            )

        response = await asyncio.wait_for(_execute_with_retry(make_call), timeout=15.0)
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"Greeting generation failed: {e}")
        return "Hey the user! Kya chal raha hai aaj?"


async def get_response(user_text: str, memory_context: str = "") -> dict:
    """
    Main LLM call. Returns response text + skill tag if present.
    """
    try:
        async def make_call():
            client = get_client()
            return await client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT.replace("{memory_context}", memory_context or "None")
                    },
                    {"role": "user", "content": user_text}
                ],
                temperature=0.8,
                max_tokens=200,
            )

        response = await asyncio.wait_for(_execute_with_retry(make_call), timeout=30.0)
        raw_text = response.choices[0].message.content.strip()

        # Extract [SKILL:...] tag
        skill = None
        if "[SKILL:" in raw_text and "]" in raw_text:
            match = re.search(r'\[SKILL:[^\]]+\]', raw_text)
            if match:
                skill = match.group(0)
                clean = raw_text.replace(skill, "").strip()
                clean = re.sub(r' {2,}', ' ', clean).strip()
            else:
                clean = raw_text
        else:
            clean = raw_text

        return {"response": clean, "skill": skill}

    except asyncio.TimeoutError:
        return {"response": "Sorry boss, thoda time lag raha hai. Dobara try karo.", "skill": None}
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        return {"response": f"Kuch gadbad ho gayi boss. Dobara try karo.", "skill": None}


async def get_response_with_skill_result(
    user_text: str,
    skill_result_text: str,
    memory_context: str = ""
) -> dict:
    """
    2nd pass LLM call — summarize skill result conversationally.
    Used for search/weather results so Max speaks them naturally.
    """
    try:
        prompt = SKILL_SUMMARY_PROMPT.replace(
            "{user_text}", user_text
        ).replace(
            "{skill_result}", skill_result_text[:800]  # cap to avoid token overflow
        )

        async def make_call():
            client = get_client()
            return await client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT.replace("{memory_context}", memory_context or "None")
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=150,
            )

        response = await asyncio.wait_for(_execute_with_retry(make_call), timeout=20.0)
        return {"response": response.choices[0].message.content.strip(), "skill": None}

    except Exception as e:
        logger.error(f"Skill result summarization failed: {e}")
        # Fallback — just return raw result truncated
        return {"response": skill_result_text[:250], "skill": None}


async def analyze_image_with_prompt(image_path: str, user_prompt: str) -> str:
    """Analyze screenshot/image using Groq Vision model."""
    try:
        client = get_client()
        with open(image_path, "rb") as f:
            b64_image = base64.b64encode(f.read()).decode("utf-8")

        resp = await client.chat.completions.create(
            model=config.VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                ]
            }]
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Vision analysis failed: {e}")
        return f"Vision Error: {str(e)}"
