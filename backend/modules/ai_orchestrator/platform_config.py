# platform_config.py — Platform settings for AI Orchestrator
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class PlatformInfo:
    name: str
    url_new_chat: str
    textarea_selectors: List[str]
    submit_selectors: List[str]
    response_selectors: List[str]
    response_done_signal: str  # 'send_button_enabled', 'text_stabilized', 'spinner_gone', 'sources_visible'
    char_limit: int
    supports_file_paste: bool
    supports_image: bool
    best_for: str = ""

PLATFORMS: Dict[str, PlatformInfo] = {
    "chatgpt": PlatformInfo(
        name="ChatGPT",
        url_new_chat="https://chatgpt.com/?model=gpt-4o",
        textarea_selectors=[
            "#prompt-textarea",
            "textarea[placeholder]",
            "div[contenteditable='true']",
            "[contenteditable='true']"
        ],
        submit_selectors=[
            "button[data-testid='send-button']",
            "button[aria-label='Send prompt']",
            "button[aria-label='Submit']",
            "button.mb-1.flex"
        ],
        response_selectors=[
            "div[data-message-author-role='assistant']",
            "div.markdown.prose",
            ".agent-turn"
        ],
        response_done_signal="send_button_enabled",
        char_limit=32000,
        supports_file_paste=True,
        supports_image=True,
        best_for="code writing, debugging, math, logic, reasoning"
    ),
    "claude": PlatformInfo(
        name="Claude",
        url_new_chat="https://claude.ai/new",
        textarea_selectors=[
            "div[contenteditable='true']",
            ".ProseMirror",
            "textarea[placeholder*='Claude']"
        ],
        submit_selectors=[
            "button[aria-label='Send Message']",
            "button[type='submit']",
            "button.bg-accent"
        ],
        response_selectors=[
            "div.font-claude-message",
            "[data-testid='assistant-message']",
            ".claude-message"
        ],
        response_done_signal="text_stabilized",
        char_limit=200000,
        supports_file_paste=True,
        supports_image=True,
        best_for="code review, security audit, deep analysis, long docs, creative writing"
    ),
    "gemini": PlatformInfo(
        name="Gemini",
        url_new_chat="https://gemini.google.com/app",
        textarea_selectors=[
            "rich-textarea div[contenteditable='true']",
            "textarea.input-area",
            "div[contenteditable='true']"
        ],
        submit_selectors=[
            "button.send-button",
            "button[aria-label='Send message']",
            ".send-button-container button"
        ],
        response_selectors=[
            "message-content.model-response-text",
            ".response-content",
            "message-content"
        ],
        response_done_signal="spinner_gone",
        char_limit=32000,
        supports_file_paste=True,
        supports_image=True,
        best_for="image understanding, quick factual questions, general queries"
    ),
    "perplexity": PlatformInfo(
        name="Perplexity",
        url_new_chat="https://www.perplexity.ai",
        textarea_selectors=[
            "textarea[placeholder]",
            "textarea.overflow-auto",
            "textarea"
        ],
        submit_selectors=[
            "button[aria-label='Submit']",
            "button.submit",
            "button[aria-label*='Submit']"
        ],
        response_selectors=[
            "div.prose",
            ".answer-text",
            "div.markdown"
        ],
        response_done_signal="sources_visible",
        char_limit=4000,
        supports_file_paste=True,
        supports_image=False,
        best_for="web research, current events, citations, general comparison"
    )
}
