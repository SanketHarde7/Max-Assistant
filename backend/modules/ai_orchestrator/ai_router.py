# Path: backend/modules/ai_orchestrator/ai_router.py
# Use: Routes user queries to appropriate AI models.
# ai_router.py — Smart platform routing logic with LRU cache
import json
import re
import time
import logging
import hashlib
from typing import Dict, Optional
from groq import AsyncGroq
from config import config
from api_utils import execute_with_retry

logger = logging.getLogger("MAX.ORCHESTRATOR.ROUTER")

# Keyword-based routing map for fast-path decisions (no API call needed)
FAST_PATH_ROUTING = {
    "chatgpt": {
        "keywords": [
            "code", "debug", "programming", "function", "algorithm", "api",
            "error", "bug", "syntax", "compile", "runtime", "database",
            "sql", "python", "javascript", "typescript", "java", "rust",
            "react", "node", "express", "fastapi", "django", "flask",
            "regex", "script", "json", "xml", "html", "css",
            "math", "calculate", "equation", "formula", "solve",
            "logic", "recursion", "loop", "variable", "class", "object"
        ],
        "patterns": [
            r"\b(write|create|generate|build|make)\b.*\b(code|script|function|program|app)\b",
            r"\b(debug|fix|solve)\b.*\b(error|bug|issue|problem)\b",
            r"\b(how\s+(do|can|to)|explain)\b.*\b(code|program|function|algorithm)\b",
        ]
    },
    "claude": {
        "keywords": [
            "review", "analyze", "audit", "security", "vulnerability",
            "document", "essay", "article", "write", "story", "creative",
            "poem", "letter", "email", "summary", "summarize",
            "long", "detailed", "comprehensive", "thorough",
            "best practice", "pattern", "architecture", "design",
            "refactor", "improve", "optimize", "clean", "structure"
        ],
        "patterns": [
            r"\b(review|audit|analyze)\b.*\b(code|project|file|repository)\b",
            r"\b(write|draft|create)\b.*\b(essay|story|article|document|email|letter)\b",
            r"\b(summarize|condense|tl;dr)\b",
            r"\b(security|vulnerability|exploit|penetration)\b",
        ]
    },
    "gemini": {
        "keywords": [
            "image", "picture", "photo", "screenshot", "screen",
            "vision", "see", "look", "visual", "diagram", "chart",
            "what is this", "identify", "recognize", "describe",
            "compare", "difference between", "vs", "versus"
        ],
        "patterns": [
            r"\b(what\s+(is|are)|identify|describe)\b.*\b(this|that|in\s+(the|this))\b.*\b(image|picture|screen)\b",
            r"\b(analyze|describe)\b.*\b(image|screenshot|picture|photo)\b",
        ]
    },
    "perplexity": {
        "keywords": [
            "news", "latest", "recent", "today", "update",
            "weather", "stock", "price", "market", "economy",
            "sports", "score", "match", "game", "player",
            "who is", "what is", "when did", "where is", "why did",
            "how to", "tutorial", "guide", "steps",
            "compare", "vs", "versus", "difference",
            "best", "top", "ranking", "review", "rating",
            "search", "find", "look up", "information about"
        ],
        "patterns": [
            r"\b(latest|recent|current|today|now)\b.*\b(news|update|information|development)\b",
            r"\b(what|who|when|where|why|how)\b.*\b(happened|is|are|was|were|did|does)\b",
            r"\b(compare|vs|versus|difference\s+between)\b",
            r"\b(best|top|ranking)\b.*\b(for|in|of)\b",
            r"\b(search|find|look\s+up)\b.*\b(for|about)\b",
        ]
    }
}

_ROUTING_PROMPT = """You are a smart AI routing agent. Based on the user's query, determine the single best AI platform to handle this query.

PLATFORM STRENGTHS:
- chatgpt: Code writing, debugging, math, logic, algorithms, technical implementation
- claude: Code review, security audit, long documents, creative writing, summarization, analysis
- gemini: Image/vision understanding, screenshot analysis, quick factual questions
- perplexity: Web research, current events, news, comparisons with citations, latest info

ROUTING EXAMPLES:
Query: "Write a Python function to sort a list" -> {"platform": "chatgpt", "reason": "Code writing task"}
Query: "Review this code for security issues" -> {"platform": "claude", "reason": "Security audit and code review"}
Query: "What's in this screenshot?" -> {"platform": "gemini", "reason": "Image analysis"}
Query: "Latest news about AI today" -> {"platform": "perplexity", "reason": "Current events research"}
Query: "Compare React vs Vue" -> {"platform": "perplexity", "reason": "Comparison with citations"}
Query: "Summarize this 50-page document" -> {"platform": "claude", "reason": "Long document analysis"}
Query: "Fix this TypeScript error" -> {"platform": "chatgpt", "reason": "Debugging task"}
Query: "What are today's stock prices?" -> {"platform": "perplexity", "reason": "Real-time data"}

User query: "{query}"

Output ONLY a JSON block:
{{"platform": "chatgpt|claude|gemini|perplexity", "reason": "short explanation", "confidence": 0.0-1.0}}"""


class AIRouter:
    def __init__(self, config):
        self.config = config
        self._cache: Dict[str, tuple] = {}  # query_hash -> (platform, timestamp)
        self._cache_ttl = 3600  # 1 hour cache TTL
        self._max_cache_size = 100

    def _get_cache_key(self, query: str) -> str:
        """Generate cache key from query."""
        normalized = query.lower().strip()
        return hashlib.md5(normalized.encode()).hexdigest()

    def _get_cached(self, query: str) -> Optional[str]:
        """Get cached routing result if valid."""
        key = self._get_cache_key(query)
        if key in self._cache:
            platform, timestamp = self._cache[key]
            if time.time() - timestamp < self._cache_ttl:
                logger.info(f"Cache hit: routing '{query[:50]}' to {platform}")
                return platform
            else:
                del self._cache[key]
        return None

    def _set_cached(self, query: str, platform: str):
        """Cache routing result."""
        if len(self._cache) >= self._max_cache_size:
            # Remove oldest entry
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        self._cache[self._get_cache_key(query)] = (platform, time.time())

    def _fast_path_route(self, query: str) -> Optional[str]:
        """
        Fast-path routing using keyword/pattern matching.
        Returns platform name or None if uncertain.
        """
        query_lower = query.lower()
        scores = {"chatgpt": 0, "claude": 0, "gemini": 0, "perplexity": 0}
        
        # Score based on keywords
        for platform, data in FAST_PATH_ROUTING.items():
            for keyword in data["keywords"]:
                if keyword in query_lower:
                    scores[platform] += 1
            
            # Score based on regex patterns (higher weight)
            for pattern in data["patterns"]:
                if re.search(pattern, query_lower):
                    scores[platform] += 3
        
        # Check for vision/screen context
        vision_keywords = ["screen", "screenshot", "image", "picture", "photo", "see this", "look at"]
        if any(kw in query_lower for kw in vision_keywords):
            scores["gemini"] += 5
        
        # Check for code context (stronger signal)
        code_patterns = [
            r"\b(code|function|class|method|variable|import|return|def\s+|const\s+|let\s+)\b",
            r"[{};]\s*\n",  # Code-like syntax
            r"\b(error|bug|debug|exception|traceback|stack trace)\b",
        ]
        for pattern in code_patterns:
            if re.search(pattern, query_lower):
                scores["chatgpt"] += 4
                break
        
        # Determine winner
        if max(scores.values()) == 0:
            return None
            
        best_platform = max(scores, key=scores.get)
        best_score = scores[best_platform]
        
        # Only use fast path if score is high enough and clearly winning
        if best_score >= 2:
            # Check if it's a clear winner (at least 2 points ahead of second best)
            second_best = sorted(scores.values(), reverse=True)[1]
            if best_score - second_best >= 2:
                logger.info(f"Fast-path routed to {best_platform} (score: {best_score})")
                return best_platform
        
        return None

    async def route_query(self, query: str) -> str:
        """
        Determines the best platform for the given query.
        Uses fast-path first, then LLM-based routing if uncertain.
        """
        # 1. Check cache
        cached = self._get_cached(query)
        if cached:
            return cached
        
        # 2. Try fast-path routing
        fast_result = self._fast_path_route(query)
        if fast_result:
            self._set_cached(query, fast_result)
            return fast_result
        
        # 3. LLM-based routing for uncertain queries
        try:
            prompt = _ROUTING_PROMPT.format(query=query[:500])  # Limit query length

            async def call():
                key = self.config.get_active_api_key()
                if not key:
                    logger.warning("No API key for AI router, using default.")
                    raise ValueError("No API key")
                client = AsyncGroq(api_key=key)
                return await client.chat.completions.create(
                    model=getattr(self.config, 'LLM_MODEL', 'llama-3.3-70b-versatile'),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=80,
                )

            resp = await execute_with_retry(call)
            raw = resp.choices[0].message.content.strip()
            data = None
            
            # Try direct JSON parse
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                pass
            
            # Try regex extraction
            if not data:
                # Look for JSON-like structure
                m = re.search(r'\{[^{}]*"platform"[^{}]*\}', raw, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(0))
                    except json.JSONDecodeError:
                        pass
            
            # Extract platform name from text if JSON fails
            if not data:
                for platform in ["chatgpt", "claude", "gemini", "perplexity"]:
                    if platform in raw.lower():
                        data = {"platform": platform}
                        break
            
            if data and "platform" in data:
                platform = data["platform"].lower().strip()
                if platform in ["chatgpt", "claude", "gemini", "perplexity"]:
                    confidence = data.get("confidence", 0.5)
                    reason = data.get("reason", "LLM routing")
                    logger.info(
                        f"LLM routed '{query[:50]}' to {platform} "
                        f"(confidence: {confidence}). Reason: {reason}"
                    )
                    self._set_cached(query, platform)
                    return platform

            logger.warning(f"Could not parse valid platform from routing response: {raw[:100]}")
        except Exception as e:
            logger.error(f"AI Routing error: {e}")

        default_platform = getattr(self.config, 'AI_DEFAULT_PLATFORM', 'chatgpt')
        logger.info(f"AI Routing fallback to default: {default_platform}")
        return default_platform
