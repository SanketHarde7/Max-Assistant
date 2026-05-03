# ═══════════════════════════════════════════════════════
# main.py CHANGES — 2 sections to update
# ═══════════════════════════════════════════════════════

# ── CHANGE 1: Add this constant near top of file ──

SEARCH_DATA_SKILLS = {"search", "weather"}  # These get 2nd LLM pass for summarization


# ── CHANGE 2: Replace _build_final_response and skill block ──
# In BOTH run_voice_pipeline and run_text_pipeline,
# replace the skill result handling block with this:

# NOTE: In run_voice_pipeline, use `transcript` as user_text
# In run_text_pipeline, use `message` as user_text

async def _handle_skill_result(
    user_text: str,
    response_text: str,
    skill_result: dict,
    context: str
) -> str:
    """
    Smart skill result handler.

    - SEARCH/WEATHER skills → 2nd LLM pass → conversational summary
    - Other DATA skills → truncated result appended
    - ACTION skills → LLM response as-is (already says what it did)
    """
    if not skill_result.get("executed"):
        return response_text

    skill_name = skill_result.get("skill_name", "")
    result_str = skill_result.get("result", "").strip()
    tts_result = skill_result.get("tts_result", "").strip()
    is_data = skill_result.get("is_data_skill", False)

    if not is_data:
        # ACTION skill — LLM response is enough
        return response_text

    if skill_name in SEARCH_DATA_SKILLS and result_str:
        # Search/weather → LLM summarizes conversationally
        try:
            summary = await llm.get_response_with_skill_result(
                user_text=user_text,
                skill_result_text=result_str,
                memory_context=context
            )
            return summary["response"]
        except Exception as e:
            logger.warning(f"2nd LLM pass failed: {e}")
            return f"{response_text} {tts_result}".strip()

    # Other data skills (find_and_explain, run_code etc.) — use truncated
    if tts_result:
        return f"{response_text} {tts_result}".strip()

    return response_text


# ── CHANGE 3: In WebSocket handler, add greeting on connect ──
# Add this right after `await websocket.accept()`:

"""
# Send greeting on connect
try:
    greeting = await llm.get_greeting()
    greeting_audio = await tts.text_to_speech(greeting)
    greeting_b64 = base64.b64encode(greeting_audio).decode("utf-8") if greeting_audio else ""

    await send("response_text", text=greeting)
    await send("status_update", state="speaking")
    if greeting_b64:
        await send("audio_response", audio=greeting_b64)
except Exception as greet_err:
    logger.warning(f"Greeting failed (non-critical): {greet_err}")
"""


# ── CHANGE 4: In run_voice_pipeline, replace skill result block ──
# Find this:
#     response_text = _build_final_response(response_text, skill_result)
# Replace with:
#     response_text = await _handle_skill_result(transcript, response_text, skill_result, context)

# ── CHANGE 5: In run_text_pipeline, same replacement ──
#     response_text = _build_final_response(response_text, skill_result)
# Replace with:
#     response_text = await _handle_skill_result(message, response_text, skill_result, context)
