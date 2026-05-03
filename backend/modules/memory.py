"""
Memory Manager Module
Handles persistent conversation history, context windowing, and auto-summarization.
Thread-safe JSON persistence with user fact extraction.
"""
import json
import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Manages conversation memory with:
    - Context window (last N messages)
    - Auto-summarization when threshold exceeded
    - Persistent JSON storage
    - User fact extraction
    """
    
    def __init__(self, memory_file: str, max_messages: int = 20, summarize_threshold: int = 20):
        self.memory_file = Path(memory_file)
        self.max_messages = max_messages
        self.summarize_threshold = summarize_threshold
        self._lock = asyncio.Lock()
        
        # Ensure data directory exists
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load or initialize memory
        self.memory = self._load_memory()
    
    def _load_memory(self) -> Dict:
        """Load memory from JSON file or return fresh structure."""
        try:
            if self.memory_file.exists():
                content = self.memory_file.read_text(encoding='utf-8').strip()
                if not content:
                    logger.warning(f"⚠️ Memory file empty, resetting: {self.memory_file}")
                    return self._fresh_memory()
                    
                data = json.loads(content)
                logger.info(f"📦 Loaded memory with {len(data.get('messages', []))} messages")
                return data
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ Memory file corrupted, resetting: {e}")
        except Exception as e:
            logger.error(f"❌ Failed to load memory: {e}")
        
        return self._fresh_memory()
    
    def _fresh_memory(self) -> Dict:
        """Create fresh memory structure."""
        return {
            "session_id": datetime.now().isoformat(),
            "messages": [],
            "summary": "",
            "user_facts": {
                "name": "Sanket",
                "location": "Maharashtra",
                "preferences": {}
            },
            "created_at": datetime.now().isoformat()
        }
    
    def _save_to_disk(self) -> bool:
        """Write memory to disk (call inside lock only)."""
        try:
            temp_file = self.memory_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.memory, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.memory_file)
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save memory to disk: {e}")
            return False
    
    async def save_memory(self) -> bool:
        """Persist memory to JSON file (thread-safe)."""
        async with self._lock:
            return self._save_to_disk()
    
    async def add_message(self, role: str, content: str) -> bool:
        """Add a message to conversation history."""
        try:
            async with self._lock:
                self.memory["messages"].append({
                    "role": role,
                    "content": content,
                    "timestamp": datetime.now().isoformat()
                })
                
                # Check if summarization needed
                if len(self.memory["messages"]) >= self.summarize_threshold:
                    self._auto_summarize_internal()
                
                # Keep only last max_messages
                if len(self.memory["messages"]) > self.max_messages:
                    self.memory["messages"] = self.memory["messages"][-self.max_messages:]
                
                return self._save_to_disk()
                
        except Exception as e:
            logger.error(f"❌ Failed to add message: {e}")
            return False
    
    def _auto_summarize_internal(self) -> bool:
        """Summarize older messages to save tokens. Must be called inside lock."""
        try:
            messages = self.memory["messages"]
            if len(messages) <= self.summarize_threshold:
                return True
            
            kept_messages = messages[:2] + messages[-10:]
            middle_messages = messages[2:-10]
            
            summary_parts = [
                f"[{m['role']}] {m['content'][:100]}..." 
                for m in middle_messages[:5]
            ]
            new_summary = " | ".join(summary_parts)
            
            self.memory["messages"] = kept_messages
            self.memory["summary"] = new_summary
            logger.info(f"📝 Auto-summarized {len(middle_messages)} messages")
            
            return True
        except Exception as e:
            logger.error(f"❌ Summarization failed: {e}")
            return False
    
    def get_context(self) -> str:
        """Build context string for LLM prompt."""
        context_parts = []
        
        if self.memory.get("summary"):
            context_parts.append(f"PREVIOUS: {self.memory['summary']}")
        
        for msg in self.memory["messages"][-self.max_messages:]:
            role = "You" if msg["role"] == "user" else "Jarvis"
            context_parts.append(f"{role}: {msg['content']}")
        
        return "\n".join(context_parts)
    
    async def clear_memory(self) -> bool:
        """Reset conversation history (keep user facts)."""
        try:
            async with self._lock:
                user_facts = self.memory.get("user_facts", {})
                self.memory = self._fresh_memory()
                self.memory["user_facts"] = user_facts
                return self._save_to_disk()
        except Exception as e:
            logger.error(f"❌ Failed to clear memory: {e}")
            return False
    
    def get_user_fact(self, key: str, default=None):
        return self.memory.get("user_facts", {}).get(key, default)
    
    async def update_user_fact(self, key: str, value) -> bool:
        """Update a user fact (async-safe)."""
        try:
            async with self._lock:
                self.memory.setdefault("user_facts", {})[key] = value
                return self._save_to_disk()
        except Exception as e:
            logger.error(f"❌ Failed to update user fact: {e}")
            return False


_memory_instance: Optional[MemoryManager] = None


def get_memory_manager(config) -> MemoryManager:
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = MemoryManager(
            memory_file=config.MEMORY_FILE,
            max_messages=config.MEMORY_MAX_MESSAGES,
            summarize_threshold=config.MEMORY_SUMMARIZE_THRESHOLD
        )
    return _memory_instance