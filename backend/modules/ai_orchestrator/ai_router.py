# ai_router.py — Smart platform routing logic
import json
import re
import logging
from groq import AsyncGroq
from config import config

logger = logging.getLogger("MAX.ORCHESTRATOR.ROUTER")

_ROUTING_PROMPT = """You are a smart AI routing agent. Based on the user's query, determine the single best AI platform to handle this query.

PLATFORM STRENGTHS & CAPABILITIES:
- chatgpt: Best for code writing, coding tasks, debugging, math, logic, reasoning, structured algorithms.
- claude: Best for code review, security audit, analyzing long documents, summarizing files, creative writing, prose, editing.
- gemini: Best for vision, image understanding, screenshot analysis, quick factual questions, general queries.
- perplexity: Best for web research, current events, news, comparison of products/options, citations, latest statistics.

User query: "{query}"

Output ONLY a JSON block like:
{{"platform": "chatgpt|claude|gemini|perplexity", "reason": "short explanation"}}"""

class AIRouter:
    def __init__(self, config):
        self.config = config

    async def route_query(self, query: str) -> str:
        """
        Determines the best platform ('chatgpt', 'claude', 'gemini', 'perplexity')
        for the given query. Falls back to default if call fails.
        """
        try:
            key = self.config.get_active_api_key()
            if not key:
                logger.warning("No API key available for AI router, falling back to default.")
                return getattr(self.config, 'AI_DEFAULT_PLATFORM', 'chatgpt')

            client = AsyncGroq(api_key=key)
            prompt = _ROUTING_PROMPT.format(query=query)

            resp = await client.chat.completions.create(
                model=self.config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=60,
            )

            raw = resp.choices[0].message.content.strip()
            data = None
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                m = re.search(r'\{[^}]+\}', raw, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(0))
                    except json.JSONDecodeError:
                        pass
            
            if data and "platform" in data:
                platform = data["platform"].lower().strip()
                if platform in ["chatgpt", "claude", "gemini", "perplexity"]:
                    logger.info(f"Routed query '{query[:50]}' to {platform}. Reason: {data.get('reason')}")
                    return platform

            logger.warning(f"Could not parse valid platform from routing response: {raw[:100]}")
        except Exception as e:
            logger.error(f"AI Routing error: {e}")

        default_platform = getattr(self.config, 'AI_DEFAULT_PLATFORM', 'chatgpt')
        logger.info(f"AI Routing fallback to default: {default_platform}")
        return default_platform
