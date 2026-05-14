"""
language_detector.py — detects if text is Hindi or English.
Uses langdetect library (works on Latin-script Hindi like "kya tum").
No Devanagari required.
"""
import logging
import re
from langdetect import detect, DetectorFactory

# Seed for consistent results
DetectorFactory.seed = 0

logger = logging.getLogger("MAX.LANG")

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

_HINDI_STRONG_WORDS = (
    "kya", "kyu", "kyun", "kaise", "kaisa", "kaisi", "kaunsa", "kaun", "kab", "kahan",
    "mujhe", "mujh", "mera", "meri", "mere", "tum", "aap", "nahi", "nahin", "haan", "han",
    "chahiye", "sakta", "sakti", "sakte", "karna", "karo", "kar", "krna", "kr",
    "batao", "bolo", "suno", "dekho", "mat", "samjha", "samjho", "samajh", "kyunki",
    "jab", "tab", "namaste", "shukriya", "sukriya", "dhanyavad",
)

_HINDI_WEAK_WORDS = (
    "main", "aur", "bhi", "hai", "ho", "hoon", "se", "pe", "ka", "ki", "ke", "mein",
    "bahut", "thoda", "thodi",
)


def _compile_word_regex(words: tuple) -> re.Pattern:
    joined = "|".join(re.escape(w) for w in words)
    return re.compile(rf"\b(?:{joined})\b", re.IGNORECASE)


_HINDI_STRONG_RE = _compile_word_regex(_HINDI_STRONG_WORDS)
_HINDI_WEAK_RE = _compile_word_regex(_HINDI_WEAK_WORDS)


def detect_language(text: str) -> str:
    """
    Returns 'hi' for Hindi, 'en' for English, or 'en' as fallback.
    """
    if not text or len(text.strip()) < 3:
        return 'en'

    try:
        lang = detect(text)
        # langdetect returns 'hi' for Hindi, 'en' for English
        if lang == 'hi':
            return 'hi'
        else:
            return 'en'
    except Exception as e:
        # If detection fails (e.g., very short ambiguous text), default to English
        logger.debug(f"Language detection failed: {e}")
        return 'en'


def is_hindi(text: str) -> bool:
    return detect_language(text) == 'hi'


def is_hindi_by_regex(text: str) -> bool:
    """
    Lightweight regex-based Hindi/Hinglish detection for text chat.
    Returns True for Devanagari or common Hinglish words.
    """
    if not text or len(text.strip()) < 2:
        return False

    if _DEVANAGARI_RE.search(text):
        return True

    if _HINDI_STRONG_RE.search(text):
        return True

    return len(_HINDI_WEAK_RE.findall(text)) >= 2