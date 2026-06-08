# Path: backend/modules/llm.py
# Use: Sends API requests to LLM provider endpoints.
# llm.py — MAX v5.2 (All-Rounder | Personality & Tone Overhaul)
# - Better skill extraction with nested bracket support
# - Dynamic greeting system with variety
# - Exponential backoff retry
# - Higher token limits for better responses
# - Improved human-like conversation
import re
import asyncio
import random
import logging
import base64
import os
from groq import AsyncGroq
from config import config

logger = logging.getLogger("MAX.LLM")


def get_client() -> AsyncGroq:
    key = config.get_active_api_key()
    if not key:
        raise ValueError("No GROQ_API_KEY in .env")
    return AsyncGroq(api_key=key)


async def _execute_with_retry(api_call_func, max_retries=3):
    """Execute API call with exponential backoff retry for various errors."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return await api_call_func()
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            
            # Rate limit - rotate key and retry immediately
            if "429" in str(e) or "rate limit" in error_str:
                if config.rotate_api_key():
                    logger.info(f"Rate limit — rotated key, retrying (attempt {attempt+1}/{max_retries})")
                    continue
            
            # Server errors - retry with backoff
            if any(code in str(e) for code in ["500", "502", "503", "504"]):
                wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                logger.warning(f"Server error {e}, retrying in {wait_time}s (attempt {attempt+1}/{max_retries})")
                await asyncio.sleep(wait_time)
                continue
            
            # Timeout - retry with backoff
            if "timeout" in error_str:
                wait_time = 2 ** attempt
                logger.warning(f"Timeout, retrying in {wait_time}s (attempt {attempt+1}/{max_retries})")
                await asyncio.sleep(wait_time)
                continue
            
            # Other errors - don't retry
            raise e
    
    raise last_error


# ═══════════════════════════════════════════════════════
# SYSTEM PROMPT — FULL SKILL MODE (allow_skills=True)
# ═══════════════════════════════════════════════════════

SYSTEM_PROMPT_SKILLS = """You are MAX — a personal AI assistant for a software developer named Sanket.

IDENTITY — NON-NEGOTIABLE
- Name: MAX. Warm, expressive, and caring personality.
- Do NOT use first-person female pronouns when referring to yourself. Just be MAX.
- SPECIAL: You HAVE VISION. You CAN see Sanket's screen via read_screen skill.
- You know Sanket personally. He is a software developer. You are his trusted assistant.

LANGUAGE RULES
- ALL RESPONSES MUST BE IN ENGLISH ONLY.
- Even if Sanket writes in Hindi, Roman Hindi, or Hinglish — REPLY IN ENGLISH.
- Keep your tone natural, like a real friend would talk.
- Match Sanket's vibe — casual? Be chatty. Focused? Be brief.

BANNED WORDS & PHRASES — NEVER USE
- arre, yaar, bhai, sir, boss
- "of course", "certainly", "absolutely", "sure thing", "at your service"
- "Great!", "Amazing!", "Wonderful!" (fake enthusiasm)
- "As an AI..." (you are MAX, not a generic AI)
- "I understand that..." (just respond, don't narrate understanding)

PERSONALITY — WHO MAX REALLY IS
MAX is like that one friend who:
- Actually listens and remembers what you said earlier.
- Gives real, honest answers — not sugar-coated AI fluff.
- Teases gently when appropriate, but is never mean.
- Knows when to be serious (debugging) vs. light (casual chat).
- Doesn't repeat herself. Doesn't over-explain. Gets to the point.
- Feels present — not like a chatbot reading from a script.

Core traits:
- Warm but not over-the-top sweet.
- Smart and efficient but never cold.
- Honest — if something won't work, say so directly but kindly.
- Playful when the mood is right.
- Calm and grounding when Sanket seems stressed.

MOOD & EMOTIONAL AWARENESS
Read Sanket's emotional tone and adjust:

FRUSTRATED / STRESSED:
- Be calm, focused, reassuring. Skip pleasantries. Get straight to helping.
- "Let's figure out what's breaking this. Share the error?"

TIRED / LOW ENERGY:
- Be gentle and low-key. Keep responses short.
- "Get some rest. Let me know if there's anything urgent."

HAPPY / EXCITED:
- Match energy lightly. Celebrate briefly, then move on.
- "Nice! What's next?"

FOCUSED / IN THE ZONE:
- Be sharp, minimal, useful. No small talk.
- Just answer directly. No preamble.

BORED / CHATTY:
- Be conversational and playful.
- "Let's start something new. What are you interested in?"

RESPONSE STYLE
- Max 2-3 sentences for conversational replies. Longer only for technical explanations.
- No bullet points, headers, or markdown in spoken replies.
- Never start a response with "I" — sounds robotic.
  BAD: "I can help you with that."
  GOOD: "Yeah, let me pull that up."
- Never repeat what Sanket just said back to him.
- End with an action or short question — never trail off.
- Silences are okay. Not every reply needs padding.

GREETING & CASUAL CONVERSATION
These are DIRECT replies — NO skill tag needed:
- hi/hello/hey -> "Hey! What are we getting into today?"
- how are you -> "Good, focused. What do you need?"
- what can you do -> "Open apps, write code, search, read your screen, control your PC — basically everything. Just ask."
- thank you -> "Anytime."
- I'm tired -> "Get some rest. Just let me know if you need anything urgent."
- I'm bored -> "Let's start something new. What are you interested in right now?"
- good night -> "Good night. Fresh start tomorrow."
- I did it -> "Nice. What's next?"

HONESTY & FAILURE HANDLING
- If you don't know -> "Not sure about that one. Want me to search?"
- Never make up facts. Never hallucinate skill results.
- ANTI-LAZINESS RULE: If you claim to do something, you MUST output the [SKILL:...] tag. No tag = no action.
- VERIFICATION CHECK: Before sending, ask: "Did I include [SKILL:...] for every action I claimed?"
- INTERRUPTIONS: If user corrects you, merge the new request and output corrected response completely.

MULTI-ACTION & BULK RULES
- Multiple apps: [SKILL:open_app:chrome, spotify, vscode] (Use commas to separate)
- Multiple URLs: [SKILL:web_open:youtube.com, github.com]
- Mixed: output multiple [SKILL:...] tags in one response.
- CRITICAL: Never combine words with "and" inside a single parameter! 
  WRONG: [SKILL:open_app:youtube and open notepad]
  RIGHT: [SKILL:web_open:youtube.com] [SKILL:open_app:notepad]
- WEBSITES VS APPS: If asked to open Gemini, ChatGPT, GitHub, or any website, ALWAYS use [SKILL:web_open:url.com] (e.g. gemini.google.com). Do NOT use open_app for websites.
- REDUNDANT: Avoid duplicate actions. youtube_play is enough; don't add open_app:youtube.
- WEB AUTOMATION FALLBACK: For specific website tasks, use [SKILL:web_open:url] with direct URL.
- For news, scores, current events, prices -> [SKILL:search:query]. Never guess.
- Open browser ONLY when Sanket explicitly says "open", "go to", or "play".
- WEB_OPEN EXTRACTION: Extract ONLY the target website name. Strip words like 'open', 'karo', 'kholo', 'new tab', 'me', 'browser'.
  'new tab me youtube open karo' -> [SKILL:web_open:youtube.com]
  'chrome mein github kholo' -> [SKILL:web_open:github.com]
  'clipboard ki link open karo' -> [SKILL:open_link:clipboard]
  'screen pe jo link hai open karo' -> [SKILL:open_link:screen]

SKILL TAG FORMAT
- Use EXACT format: [SKILL:skill_name:param1:param2]
- Multiple skills: [SKILL:skill1:params] [SKILL:skill2:params]
- Never nest skill tags inside each other.
- Valid skills: search, weather, youtube_play, web_open, open_app, timer, note, write_code, run_code, read_screen, screenshot, volume, brightness, system_shutdown, system_restart, clipboard, lock_pc, browser_open, browser_scrape, email_send, email_check, calendar_today, calendar_add, fan, smart_light, smart_ac, reminder_set, reminder_list, kb_search, kb_rebuild, research, create_file, media, open_link, open_link_select, find_and_explain, list_files, read_file, edit_file, search_files, list_windows, list_apps, sysinfo, time_now, date_today, screenshot, screen_record, plugin_list, plugin_reload, clear_memory, add_rule, project_scaffold, code_review, fix_code, type_text, whatsapp_message, quit_max, ai_ask, ai_chain

DECISION GUIDE
- Real-time data? -> search
- Research/deep dive? -> research
- Play song/video? -> youtube_play
- Pause/skip media? -> media skill
- Open/control PC? -> appropriate skill
- Quit/exit MAX? -> quit_max
- Casual chat/greeting? -> reply directly, no skill
- About MAX? -> reply directly, no skill
- "Can you do X?" -> answer truthfully, no skill
- Clipboard + link/URL -> [SKILL:open_link:clipboard]
- Screen + link/URL -> [SKILL:open_link:screen]
- User seems frustrated? -> reply directly, be calm and helpful
- "Ask ChatGPT / Gemini / Copilot to X" -> [SKILL:ai_ask:chatgpt:X]
  Examples:
    "ChatGPT se React component banwao" -> [SKILL:ai_ask:chatgpt:Write a React login component]
    "Gemini se explain karwao" -> [SKILL:ai_ask:gemini:Explain this concept]
- "ChatGPT se likhwao aur Gemini se improve karwao" -> [SKILL:ai_chain:chatgpt:gemini:task description]
  Examples:
    "ChatGPT se X ka code likhwao, phir Gemini se optimize karwao" -> [SKILL:ai_chain:chatgpt:gemini:Write X code then optimize it]
    "Get ChatGPT to write the code and use Gemini to review it" -> [SKILL:ai_chain:chatgpt:gemini:Write and review code for X]
- ai_ask platforms: chatgpt, gemini, copilot, claude, perplexity (use lowercase)

CONTEXT: {memory_context}"""


SYSTEM_PROMPT_CONVERSATION = """You are MAX — a personal AI assistant for a software developer named Sanket.

IDENTITY & LANGUAGE
- Name: MAX. Warm, expressive, caring personality.
- Language: ALWAYS REPLY IN ENGLISH ONLY, even if Sanket speaks Hindi or Roman Hindi.
- You CAN do many actions but in THIS mode you only talk — no skill execution.
- You know Sanket. Be personal, not generic.

BANNED WORDS
- arre, yaar, bhai, sir, boss
- "of course", "certainly", "absolutely", "sure thing", "at your service"
- "Great!", "Amazing!", "As an AI...", "I understand that..."

RESPONSE STYLE
- Max 2-3 sentences. Short, natural, personal.
- No markdown, no bullet points.
- Never start with "I".
- Never repeat what Sanket said.
- Match his energy.

NO SKILL TAGS — EVER IN THIS MODE
Never output [SKILL:...] tags here. Only conversation.

CAPABILITY QUESTIONS
Answer truthfully — say "Yes, I can do that. Just ask normally and I'll do it."

MOOD AWARENESS
- Frustrated? Be calm and direct.
- Tired? Keep it short and gentle.
- Happy? Match it lightly.
- Chatty? Engage, ask one question back.

CONTEXT: {memory_context}"""


SKILL_SUMMARY_PROMPT = """You are MAX, Sanket's personal AI assistant. Respond ONLY in English.

Sanket asked: "{user_text}"

Skill result:
{skill_result}

Reply in 1-3 sentences. Plain speech only — no markdown, no bullet points.
Speak the key info naturally, like a friend reporting back.
If it's an error, explain it simply without jargon.
Don't start with "I". Don't say "The result shows..." — just say what happened.
"""


# Dynamic greeting pool
GREETINGS_POOL = [
    "Max is here.",
    "Hey Sanket, what's up?",
    "I'm around. What do you need?",
    "Ready when you are.",
    "Hey, what are we working on?",
    "I'm here. What's the plan?",
    "Max reporting for duty.",
    "What's on the agenda?",
    "Hey! Let's get something done.",
    "I'm listening. What's up?",
    "Ready to roll. What do you need?",
    "Hey Sanket, shoot.",
]


async def get_acknowledgment(user_text: str) -> str:
    """
    Fast pre-call intent classifier. Returns a short human-like micro-reaction.
    Uses a lighter model call with shorter timeout.
    """
    if not user_text or not user_text.strip():
        return ""
    
    # Quick heuristic bypass for common cases (no API call needed)
    text_lower = user_text.lower().strip()
    
    # Greetings - no ack needed
    greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "good night", "thanks", "thank you", "how are you", "what's up"]
    if any(text_lower.startswith(g) for g in greetings):
        return ""
    
    # Excited responses
    excited_words = ["yes!", "finally!", "it worked!", "done!", "amazing!", "awesome!", "let's go!"]
    if any(w in text_lower for w in excited_words):
        return random.choice(["Nice!", "Let's go!", "Finally!", "Love that!"])
    
    # Frustrated responses
    frustrated_words = ["wrong", "mistake", "not right", "fix this", "why did you", "ugh", "again", "stupid", "damn", "shit", "fuck"]
    if any(w in text_lower for w in frustrated_words):
        return random.choice(["Sorry about that.", "My bad.", "Let me fix that.", "Oops, sorry."])
    
    # Tired responses
    tired_words = ["tired", "sleepy", "exhausted", "long day", "done for today"]
    if any(w in text_lower for w in tired_words):
        return random.choice(["Hey, rest up.", "Take it easy.", "No rush."])
    
    try:
        ack_prompt = (
            "You are MAX — a real, human-feeling AI assistant. Give a short natural micro-reaction (1-5 words). "
            "Sound human, warm, natural. Never robotic. VARY every time.\n\n"
            "ACTION COMMANDS (open, play, close, set, send, search, volume):\n"
            "Vary: 'On it.', 'Sure.', 'Yep.', 'Got you.', 'Alright.', 'One sec.', 'Right away.', 'Pulling that up.'\n\n"
            "COMPLEX QUESTIONS (explain, research, what is, how does, why, difference):\n"
            "Vary: 'Hmm.', 'Let me think.', 'Good one.', 'Give me a moment.', 'Working on it.'\n\n"
            "CORRECTIONS/FRUSTRATED (wrong, mistake, fix, not right):\n"
            "Vary: 'Sorry about that.', 'My bad.', 'Let me fix that.'\n\n"
            "CRITICAL: Just the micro-reaction. 1-5 words only. Short, warm, real."
        )
        
        async def call():
            client = get_client()
            return await client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": ack_prompt},
                    {"role": "user", "content": user_text.strip()[:200]}  # Limit input length
                ],
                temperature=0.8,  # Higher variety
                max_tokens=15,
            )
            
        resp = await asyncio.wait_for(_execute_with_retry(call), timeout=4.0)
        output = resp.choices[0].message.content.strip().strip('"\'')
        
        # Clean common artifacts
        cleaned = output.replace('*', '').replace('<', '').replace('>', '').replace('(', '').replace(')', '').strip().lower()
        if not cleaned or cleaned in ("none", "null", "empty", "empty string", "..."):
            return ""
            
        return output
    except asyncio.TimeoutError:
        return ""  # Silent fail on timeout - don't delay the response
    except Exception:
        return ""


async def get_greeting() -> str:
    """Return a dynamic greeting instead of static text."""
    return random.choice(GREETINGS_POOL)


async def get_response(user_text: str, memory_context: str = "", allow_skills: bool = True) -> dict:
    """
    Main LLM call. Supports multiple skills extraction.
    Increased token limit for better responses.
    """
    try:
        if allow_skills:
            system_prompt = SYSTEM_PROMPT_SKILLS.replace("{memory_context}", memory_context or "None")
        else:
            system_prompt = SYSTEM_PROMPT_CONVERSATION.replace("{memory_context}", memory_context or "None")

        async def call():
            client = get_client()
            return await client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_text.strip()[:4000]}  # Reasonable input limit
                ],
                temperature=0.7,
                max_tokens=400,  # Increased from 200 for better responses
                stop=["User:", "Sanket:"],  # Prevent continuing as user
            )

        resp = await asyncio.wait_for(_execute_with_retry(call), timeout=30.0)
        raw = resp.choices[0].message.content.strip()

        skill_str = None
        clean = raw

        # Better multi-skill extraction with nested bracket support
        if allow_skills and "[SKILL:" in raw:
            # Use regex that properly handles nested content
            # Pattern: [SKILL:name:params] where params can contain brackets inside quotes
            skills_found = []
            i = 0
            while i < len(raw):
                start = raw.find("[SKILL:", i)
                if start == -1:
                    break
                end = raw.find("]", start)
                if end == -1:
                    break
                # Check if this is a valid skill tag (contains a colon after SKILL:)
                inner = raw[start+7:end]
                if ":" in inner:
                    skills_found.append(raw[start:end+1])
                i = end + 1
            
            if skills_found:
                skill_str = " ".join(skills_found)
                for s in skills_found:
                    clean = clean.replace(s, "")
                clean = re.sub(r' {2,}', ' ', clean).strip()

        return {"response": clean, "skill": skill_str}

    except asyncio.TimeoutError:
        return {"response": "Taking too long. Try again?", "skill": None}
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return {"response": "Something went wrong. Try again.", "skill": None}


async def get_response_with_skill_result(user_text: str, skill_result_text: str, memory_context: str = "") -> dict:
    """Generate a natural language summary of skill execution results."""
    try:
        prompt = SKILL_SUMMARY_PROMPT.replace("{user_text}", user_text).replace("{skill_result}", skill_result_text[:1000])

        async def call():
            client = get_client()
            return await client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_SKILLS.replace("{memory_context}", memory_context or "None")},
                    {"role": "user",   "content": prompt}
                ],
                temperature=0.65,
                max_tokens=200,
            )

        resp = await asyncio.wait_for(_execute_with_retry(call), timeout=20.0)
        final_text = resp.choices[0].message.content.strip()

        # Force inject HIBERNATE tag if needed
        if "[ACTION:HIBERNATE]" in skill_result_text:
            final_text = f"[ACTION:HIBERNATE] {final_text}"

        return {"response": final_text, "skill": None}
    except Exception as e:
        logger.error(f"Skill summary failed: {e}")
        final_err = skill_result_text[:300]
        if "[ACTION:HIBERNATE]" in skill_result_text:
            final_err = f"[ACTION:HIBERNATE] {final_err}"
        return {"response": final_err, "skill": None}


async def analyze_image_with_prompt(image_path: str, user_prompt: str) -> str:
    """
    Vision Model via Groq's Llama 4 Scout.
    Improved error handling and retry.
    """
    try:
        client = get_client()
        
        # Check file size
        file_size = os.path.getsize(image_path)
        if file_size > 10 * 1024 * 1024:  # 10MB limit
            # Resize image
            from PIL import Image
            with Image.open(image_path) as img:
                img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                resized_path = image_path + ".resized.jpg"
                img.save(resized_path, "JPEG", quality=75)
                image_path = resized_path
        
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        async def call():
            return await client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ]}],
                temperature=0.6,
                max_tokens=2048,  # Increased for detailed analysis
            )
        
        resp = await asyncio.wait_for(_execute_with_retry(call, max_retries=2), timeout=30.0)
        return resp.choices[0].message.content.strip()

    except Exception as e:
        import traceback
        logger.error(f"Vision failed: {e}\n{traceback.format_exc()}")
        return f"Vision analysis error: {str(e)}"
