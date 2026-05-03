# ═══════════════════════════════════════════════════════
# REPLACE _skill_web_search in skills.py with this version
# Uses Google News RSS → actual headlines, no browser opening
# ═══════════════════════════════════════════════════════

def _skill_web_search(self, *args) -> str:
    """
    Search web using Google News RSS (free, no API key).
    Returns actual text content — not browser URL.

    FIX: DuckDuckGo Instant Answer returns empty AbstractText for
    sports/news queries → was falling back to browser open.
    Google News RSS always returns real headlines.
    """
    import httpx
    import xml.etree.ElementTree as ET

    query = " ".join(args).strip()
    if not query:
        return "Kya search karna hai sir?"

    # ── Try Google News RSS first ──
    # Best for: news, sports, current events, IPL, politics etc.
    try:
        encoded_query = query.replace(" ", "+")
        rss_url = (
            f"https://news.google.com/rss/search"
            f"?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
        )
        with httpx.Client(timeout=7.0) as client:
            resp = client.get(rss_url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                items = root.findall('.//item')[:4]

                if items:
                    headlines = []
                    for item in items:
                        title_el = item.find('title')
                        if title_el is not None and title_el.text:
                            # Clean title — remove " - Source Name" suffix
                            title = title_el.text.strip()
                            if " - " in title:
                                title = title.rsplit(" - ", 1)[0]
                            headlines.append(title)

                    if headlines:
                        if len(headlines) == 1:
                            return headlines[0]
                        joined = ". ".join(headlines[:3])
                        return joined

    except Exception as e:
        logger.warning(f"Google News RSS failed: {e}")

    # ── Fallback: DuckDuckGo Instant Answer ──
    # Works for: definitions, facts, general knowledge
    try:
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        with httpx.Client(timeout=5.0) as client:
            data = client.get("https://api.duckduckgo.com/", params=params).json()
            abstract = data.get("AbstractText", "").strip()
            if abstract:
                return abstract[:300]
    except Exception:
        pass

    # ── Last fallback: open browser (only if both above fail) ──
    import webbrowser
    webbrowser.open(f"https://duckduckgo.com/?q={query.replace(' ', '+')}")
    return f"Search results browser mein khole sir '{query}' ke liye."


# ═══════════════════════════════════════════════════════
# ALSO update main.py pipeline for search/data skills
# After skill result comes, pass it back to LLM for
# conversational summarization (2-pass for DATA skills)
# ═══════════════════════════════════════════════════════

# In run_voice_pipeline and run_text_pipeline,
# REPLACE this block:

#     if is_data and result_str:
#         response_text = f"{clean_text} {tts_result}".strip()

# WITH this (uses LLM to summarize search results conversationally):

"""
SEARCH_DATA_SKILLS = {"search", "weather"}  # Skills that need LLM summarization

if skill_result.get("executed") and skill_result.get("is_data_skill"):
    skill_name = skill_result.get("skill_name")
    result_str = skill_result.get("result", "")

    if skill_name in SEARCH_DATA_SKILLS and result_str:
        # 2nd LLM pass — summarize result conversationally
        summary = await llm.get_response_with_skill_result(
            user_text=transcript,         # original user query
            skill_result_text=result_str,
            memory_context=context
        )
        response_text = summary["response"]
    else:
        # Other data skills — use truncated result directly
        response_text = _build_final_response(response_text, skill_result)
"""
