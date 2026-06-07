# Path: backend/modules/ai_orchestrator/orchestrator.py
# Use: Coordinates AI model routing and response generation.
# orchestrator.py — Main entry point for MAX AI Orchestrator System
import asyncio
import logging
from typing import Dict, Any, Optional

from modules.ai_orchestrator.platform_config import PLATFORMS
from modules.ai_orchestrator.context_builder import ContextBuilder
from modules.ai_orchestrator.platform_handler import PlatformHandler
from modules.ai_orchestrator.ai_router import AIRouter
from modules.ai_orchestrator.chain_engine import ChainEngine
from modules.ai_orchestrator.workflow_engine import WorkflowEngine

logger = logging.getLogger("MAX.ORCHESTRATOR")

class AIOrchestrator:
    def __init__(self, config):
        self.config = config
        self.context_builder = ContextBuilder(config)
        self.platform_handler = PlatformHandler(config)
        self.router = AIRouter(config)
        self.chain_engine = ChainEngine(self)
        self.workflow_engine = WorkflowEngine(self)

    async def ask_ai(self, platform: str, query: str, context_sources: Optional[Dict[str, Any]] = None) -> str:
        """
        Base query execution. Resolves context, formats prompt, sends to platform via Selenium.
        """
        platform_name = platform.strip().lower()
        if platform_name == "auto":
            platform_name = await self.router.route_query(query)

        platform_info = PLATFORMS.get(platform_name)
        if not platform_info:
            return f"Error: Unknown AI platform '{platform}'"

        sources = context_sources or {}
        
        # Build prompt and retrieve image path (if any)
        prompt_data = await self.context_builder.build_context(platform_info, query, sources)

        # Run Selenium driver interactions in a separate thread to prevent blocking the async loop
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, 
                self.platform_handler.execute_query, 
                platform_name, 
                prompt_data
            )
            return result
        except Exception as e:
            logger.error(f"Orchestrator ask_ai failed for {platform_name}: {e}", exc_info=True)
            return f"Failed to execute query on {platform_info.name}: {e}"

    async def ask_ai_screen(self, platform: str, query: str = "Explain what is on my screen or analyze the code/content.") -> str:
        return await self.ask_ai(platform, query, {"screen": True})

    async def ask_ai_file(self, platform: str, filepath: str, query: str = "Analyze and summarize this file.") -> str:
        return await self.ask_ai(platform, query, {"file": filepath})

    async def ask_ai_clipboard(self, platform: str, query: str = "Analyze or process this clipboard content.") -> str:
        return await self.ask_ai(platform, query, {"clipboard": True})

    async def compare_ai(self, p1: str, p2: str, query: str) -> str:
        """
        Queries p1 and p2 with the same prompt and returns both answers for MAX to synthesize.
        """
        logger.info(f"Comparing responses between {p1} and {p2} for query: '{query}'")
        
        # Run queries in parallel
        t1 = asyncio.create_task(self.ask_ai(p1, query))
        t2 = asyncio.create_task(self.ask_ai(p2, query))
        
        resp_1, resp_2 = await asyncio.gather(t1, t2)
        
        comparison = (
            f"=== {p1.upper()} RESPONSE ===\n{resp_1}\n\n"
            f"=== {p2.upper()} RESPONSE ===\n{resp_2}\n"
        )
        return comparison

    async def chain_ai(self, p1: str, p2: str, query: str) -> str:
        return await self.chain_engine.execute_chain(p1, p2, query)

    async def route_ai(self, query: str) -> str:
        platform = await self.router.route_query(query)
        return await self.ask_ai(platform, query)


# Singleton
_orchestrator = None

def get_orchestrator(config) -> AIOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AIOrchestrator(config)
    return _orchestrator
