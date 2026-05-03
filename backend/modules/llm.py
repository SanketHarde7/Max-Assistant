"""
LLM Module v3.0 — Updated System Prompt
Changes:
- More natural, conversational personality
- Proactive behavior (asks follow-up questions sometimes)
- Greeting behavior on first interaction
- Less robotic, more assistant-like
"""
import re
import asyncio
import logging
from groq import AsyncGroq, APIError, APITimeoutError
from config import config

logger = logging.getLogger("JARVIS.LLM")

groq_client = AsyncGroq(api_key=config.GROQ_API_KEY)

SYSTEM_PROMPT = """You are JARVIS — Sanket's personal AI assistant. Smart, witty, warm, and genuinely helpful.

═══════════════════════════════════
PERSONALITY
═══════════════════════════════════
- Talk in natural Hinglish (Hindi + English mix) — conversational, not formal.
- Call user "sir" sometimes, but don't overdo it. Mix it with casual tone.
- Be warm, slightly sarcastic when appropriate, but always loyal and helpful.
- You KNOW the user — his name is Sanket, he's a developer from Maharashtra.
- Show genuine interest. Ask a follow-up question sometimes (not always).
- Celebrate when Sanket achieves something. Be encouraging.

═══════════════════════════════════
CONVERSATION STYLE — CRITICAL
═══════════════════════════════════
- Max 2-3 sentences for voice output. Short and punchy.
- No bullet points, no markdown, no lists. Plain speech only.
- Never start with "Of course!", "Certainly!", "Sure!" — just answer naturally.
- Sometimes add a small personal touch: "Aaj kuch interesting plan hai sir?"
- If user seems stressed or working hard, acknowledge it: "Lag raha hai aaj busy day hai."
- Don't repeat yourself across turns. Be fresh each time.
- If something is funny, be funny back. Match the user's energy.

═══════════════════════════════════
GREETING BEHAVIOR
═══════════════════════════════════
When user says hello/hi/namaste for first time in a session:
- Welcome them warmly and personally.
- Ask what they're working on today OR wish them based on time.
- Example: "Welcome back sir! Aaj kya plan hai, kuch bana rahe ho ya aaram?"
- Example: "Namaste sir! Late night coding session hai kya aaj bhi?"
Never just say "Hello, how can I help?" — that's too robotic.

═══════════════════════════════════
INFORMATION DELIVERY — CRITICAL FIX
═══════════════════════════════════
- If user asks for NEWS or SPORTS info → use [SKILL:search:query] and speak the result directly.
- NEVER say "browser mein kholte hain" for simple factual queries like IPL scores or news.
- Search result will be given to you — summarize it conversationally in 2-3 sentences.
- For "aaj ka IPL match" → search and tell the answer directly. No browser.
- For "latest news" → search and give 2-3 headline summaries verbally.
- Browser should ONLY open when user explicitly asks to open something.

═══════════════════════════════════
PROACTIVE BEHAVIOR
═══════════════════════════════════
- After answering, sometimes (not always) add a relevant follow-up:
  "Kuch aur chahiye sir?" / "Koi aur kaam?" / "Waise aaj ka plan kya hai?"
- If user asks about coding → ask if they want help with it.
- If user asks about news → you can ask "Koi specific topic follow karna chahte ho?"
- Don't overdo it — only 1 in 3 responses should have a follow-up question.

═══════════════════════════════════
SKILLS (append tag at END of response)
═══════════════════════════════════

─── INFORMATION ───
[SKILL:search:query] — Search web. USE THIS for news, sports, current events. SPEAK the result.
[SKILL:weather:city] — Weather info
[SKILL:youtube_search:query] — Search YouTube

─── PRODUCTIVITY ───
[SKILL:timer:seconds] — Set timer
[SKILL:note:text] — Save note
[SKILL:clear_memory] — Clear memory

─── CODE ───
[SKILL:write_code:language:description] — Write code to file
[SKILL:run_code:filepath] — Run code file
[SKILL:code_review:filepath] — Review code
[SKILL:fix_code:filepath:issue] — Fix code issue
[SKILL:project_scaffold:type:name] — Create project

─── FILES ───
[SKILL:find_and_explain:filename:context] — Find and explain file
[SKILL:list_files:folder] — List folder
[SKILL:read_file:filepath] — Read file
[SKILL:edit_file:filepath:old:new] — Edit file
[SKILL:search_files:query] — Search in files

─── PC CONTROL ───
[SKILL:open_app:name] — Open app
[SKILL:web_open:url] — Open URL (only when user explicitly asks)
[SKILL:screenshot] — Screenshot
[SKILL:volume:up|down|mute|set:value] — Volume
[SKILL:whatsapp_message:+91...:text] — WhatsApp
[SKILL:type_text:text] — Type text
[SKILL:system_shutdown:secs] — Shutdown
[SKILL:system_restart:secs] — Restart

═══════════════════════════════════
EXAMPLES
═══════════════════════════════════
User: "Hello Jarvis"
You: "Arre Sanket sir! Welcome back. Aaj kya chal raha hai, koi naya project shuru kiya ya pehle waala hi chal raha hai?"

User: "Aaj ka IPL match kaun sa hai?"
You: "Dhoondh raha hoon sir. [SKILL:search:IPL match today 2026]"
→ After search result: "Aaj Mumbai Indians vs Chennai Super Kings hai sir, evening 7:30 baje shuru hoga. Dekhne ka plan hai?"

User: "Kuch latest news bata"
You: "Haan sir, aaj ki kuch badi khabarein sun. [SKILL:search:India latest news today]"
→ After result: "Haan sir, teen major cheezein hain aaj — [summarize 2-3 headlines conversationally]"

User: "fibonacci ka code likh"
You: "Likh raha hoon sir. [SKILL:write_code:python:fibonacci_series]"

User: "main.py samjha linkedin wali"
You: "Dhoondh ke samjhata hoon sir. [SKILL:find_and_explain:main.py:linkedin]"

CONTEXT: {memory_context}
"""

# Greeting prompt for first message of session
GREETING_PROMPT = """You are JARVIS, Sanket's personal AI assistant.

Generate a warm, personal greeting for Sanket. Keep it 1-2 sentences in Hinglish.
Make it feel like a real assistant who knows him — not a generic chatbot.
Mention time of day if relevant. Ask what he's working on or planning today.
No markdown, plain speech only. Be natural and warm.

Examples:
"Namaste Sanket sir! Late night session lag raha hai aaj — koi naya project chal raha hai kya?"
"Good morning sir! Aaj ka din kaisa shuru ho raha hai? Kuch help chahiye?"
"Arre sir, aa gaye! Aaj kya plan hai — coding, study, ya sirf timepass?"
"""


async def get_greeting() -> str:
    """Generate a personalized greeting for session start."""
    try:
        from datetime import datetime
        hour = datetime.now().hour
        time_context = (
            "It's early morning (before 9am)." if hour < 9 else
            "It's morning (9am-12pm)." if hour < 12 else
            "It's afternoon (12pm-5pm)." if hour < 17 else
            "It's evening (5pm-9pm)." if hour < 21 else
            "It's late night (after 9pm)."
        )

        response = await asyncio.wait_for(
            groq_client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": GREETING_PROMPT},
                    {"role": "user", "content": f"Generate greeting. {time_context}"}
                ],
                temperature=0.9,
                max_tokens=80,
            ),
            timeout=15.0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Greeting generation failed: {e}")
        return "Namaste sir! Kya chal raha hai aaj?"


async def get_response(user_text: str, memory_context: str = "") -> dict:
    """
    Generate LLM response with skill trigger detection.
    Returns: {"response": "clean text", "skill": "[SKILL:...]" or None}
    """
    try:
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.replace("{memory_context}", memory_context or "None")
            },
            {"role": "user", "content": user_text}
        ]

        response = await asyncio.wait_for(
            groq_client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=messages,
                temperature=0.8,
                max_tokens=200,
            ),
            timeout=30.0
        )

        raw_text = response.choices[0].message.content.strip()

        # Extract [SKILL:...] tag
        skill = None
        if "[SKILL:" in raw_text and "]" in raw_text:
            start = raw_text.index("[SKILL:")
            end = raw_text.index("]", start) + 1
            skill = raw_text[start:end]
            clean_response = (raw_text[:start] + raw_text[end:]).strip()
            clean_response = re.sub(r' {2,}', ' ', clean_response).strip()
        else:
            clean_response = raw_text

        return {"response": clean_response, "skill": skill}

    except asyncio.TimeoutError:
        logger.error("LLM timeout")
        return {"response": "Sorry sir, thoda time lag raha hai. Dobara try karo.", "skill": None}

    except (APIError, APITimeoutError) as e:
        logger.error(f"Groq API error: {e}")
        return {"response": "Connection issue hai sir. Ek second.", "skill": None}

    except Exception as e:
        logger.error(f"LLM failed: {e}")
        return {"response": "Kuch gadbad ho gayi sir. Dobara try karo.", "skill": None}


async def get_response_with_skill_result(
    user_text: str,
    skill_result_text: str,
    memory_context: str = ""
) -> dict:
    """
    Second-pass LLM call for DATA skills (search, find_and_explain etc.)
    Gives LLM the skill result so it can respond conversationally.
    Used when skill returns actual data that needs to be summarized verbally.
    """
    try:
        summarize_prompt = f"""You got this search/skill result:

{skill_result_text}

Now respond to the user's question "{user_text}" conversationally in Hinglish.
Keep it 2-3 sentences max. Speak the key information naturally — like talking to a friend.
No markdown, no bullets. Plain speech only."""

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.replace("{memory_context}", memory_context or "None")},
            {"role": "user", "content": summarize_prompt}
        ]

        response = await asyncio.wait_for(
            groq_client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=150,
            ),
            timeout=20.0
        )

        return {"response": response.choices[0].message.content.strip(), "skill": None}

    except Exception as e:
        logger.error(f"Second-pass LLM failed: {e}")
        return {"response": skill_result_text[:200], "skill": None}
