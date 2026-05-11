"""
gatekeeper.py — MAX v4.2
Post-processes LLM output before UI + TTS.
- Removes banned words that still leak through
- Gender correction: MAX is male (she/her → he/his)
- Strips leaked skill tags, markdown artifacts
- TTS-specific cleanup (emojis, length trim)
"""
import re
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger("MAX.GATEKEEPER")


class _Rule:
    __slots__ = ("regex", "replacement")

    def __init__(self, pattern: str, replacement: str, flags: int = re.IGNORECASE):
        self.regex = re.compile(pattern, flags)
        self.replacement = replacement

    def apply(self, text: str) -> str:
        return self.regex.sub(self.replacement, text)


class ResponseGatekeeper:
    """
    Applied to every LLM response before it reaches the UI and TTS.

    Rule order:
      1. Banned casual words
      2. Gender correction (MAX is male)
      3. Leaked skill tags / markdown
      4. Whitespace / punctuation cleanup
    """

    # ── 1. Banned words ──────────────────────────────────
    # Specific multi-word combos first, then single words.
    _BANNED: List[Tuple[str, str]] = [
        (r"\barre\s+bhai\b",               ""),
        (r"\barre\s+yaar\b",               ""),
        (r"\barre\s+boss\b",               ""),
        (r"\barre\b",                      ""),
        (r"\byaar\b",                      ""),
        (r"(?<![a-zA-Z])bhai(?![a-zA-Z])", ""),
        (r"\bsir\b",                       ""),
        # Over-polite openers
        (r"^(of course|certainly|absolutely|sure thing)[!,.]?\s*", ""),
    ]

    # ── 2. Gender correction ─────────────────────────────
    # MAX is male — fix any female pronouns used in self-reference.
    # These patterns are conservative to avoid flipping pronouns
    # in quoted content or user-facing descriptions.
    _GENDER: List[Tuple[str, str]] = [
        # "I am she" / "I'm she" type constructs
        (r"\bI(?:'m| am) she\b",        "I am MAX"),
        # "she said" / "she can" when referring to MAX in 3rd person
        (r"\bshe(?= (is|was|can|will|has|said|told|knows|thinks|does|helped|handled))\b", "he"),
        # Possessive "her" used for MAX
        (r"\bher(?= (response|reply|answer|voice|name|output|code|suggestion|recommendation))\b", "his"),
    ]

    # ── 3. Artifact cleanup ───────────────────────────────
    _ARTIFACTS: List[Tuple[str, str]] = [
        (r"\[SKILL:[^\]]*\]",  ""),   # Leaked skill tags
        (r"\[[A-Z_]+:[^\]]*\]", ""),   # Other bracket patterns
    ]

    # ── 4. Whitespace / punctuation ──────────────────────
    _CLEANUP: List[Tuple[str, str]] = [
        (r"[ \t]{2,}",    " "),
        (r"^\s*[,;!]\s*", ""),
        (r"\s*[,;]\s*$",  ""),
        (r"\n{3,}",       "\n\n"),
    ]

    # ── TTS extra: remove visuals ─────────────────────────
    _TTS_EXTRA: List[Tuple[str, str]] = [
        (r"\*+",  ""),
        (r"#+\s*", ""),
        (r"`+",   ""),
        (r"_{2,}", ""),
        (r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF]", ""),
    ]

    def __init__(self, extra_banned: Optional[List[str]] = None):
        build = lambda rules, flags=re.IGNORECASE: [_Rule(p, r, flags) for p, r in rules]

        self._banned_rules   = build(self._BANNED)
        self._gender_rules   = build(self._GENDER)
        self._artifact_rules = build(self._ARTIFACTS)
        self._cleanup_rules  = build(self._CLEANUP, 0)
        self._tts_rules      = build(self._TTS_EXTRA, 0)

        if extra_banned:
            for word in extra_banned:
                escaped = re.escape(word.lower())
                self._banned_rules.append(_Rule(rf"(?<![a-zA-Z]){escaped}(?![a-zA-Z])", ""))

    def filter(self, text: str) -> str:
        """Standard filter for UI display."""
        if not text or not text.strip():
            return text

        result = text
        for rule in [*self._banned_rules, *self._gender_rules, *self._artifact_rules]:
            result = rule.apply(result)
        for rule in self._cleanup_rules:
            result = rule.apply(result)

        result = result.strip()
        if result and result[0].islower():
            result = result[0].upper() + result[1:]

        if result != text:
            logger.debug(f"Gatekeeper: '{text[:70]}' → '{result[:70]}'")
        return result

    def filter_for_tts(self, text: str, max_chars: int = 300) -> str:
        """Aggressive filter for TTS — strips emojis, markdown, trims to sentence boundary."""
        result = self.filter(text)
        for rule in self._tts_rules:
            result = rule.apply(result)
        result = re.sub(r" {2,}", " ", result).strip()

        if len(result) > max_chars:
            trunc = result[:max_chars]
            last = max(trunc.rfind(". "), trunc.rfind("! "), trunc.rfind("? "))
            result = trunc[:last + 1].strip() if last > max_chars // 3 else trunc.rstrip(" ,;")

        return result.strip()


_gatekeeper: Optional[ResponseGatekeeper] = None


def get_gatekeeper(extra_banned: Optional[List[str]] = None) -> ResponseGatekeeper:
    global _gatekeeper
    if _gatekeeper is None:
        _gatekeeper = ResponseGatekeeper(extra_banned)
        logger.info("Gatekeeper initialized")
    return _gatekeeper
