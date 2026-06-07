# chain_engine.py — Sequential platform execution for AI Orchestrator
import logging
from modules.ai_orchestrator.platform_config import PLATFORMS

logger = logging.getLogger("MAX.ORCHESTRATOR.CHAIN")

class ChainEngine:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    async def summarize_response(self, text: str, max_chars: int) -> str:
        try:
            from groq import AsyncGroq
            key = self.orchestrator.config.get_active_api_key()
            if not key:
                return text[:max_chars]
            
            client = AsyncGroq(api_key=key)
            prompt = f"Summarize the following text so that it fits within {max_chars} characters while retaining all critical technical details and structures:\n\n{text}"
            
            resp = await client.chat.completions.create(
                model=self.orchestrator.config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Failed to summarize chain output: {e}")
            return text[:max_chars]

    async def execute_chain(self, p1: str, p2: str, query: str, context_sources: dict = None) -> str:
        """
        Executes query on p1 first, then feeds the output into p2 along with the query instructions.
        """
        logger.info(f"Initiating chain: {p1} -> {p2} with query: '{query}'")
        
        # Step 1: Execute Platform 1
        logger.info(f"Chain Step 1: Querying {p1}...")
        resp_1 = await self.orchestrator.ask_ai(p1, query, context_sources)
        if not resp_1:
            raise RuntimeError(f"Chain failed: no response received from {p1}")

        # Step 2: Check limit of Platform 2 and summarize if necessary
        p2_info = PLATFORMS.get(p2.lower())
        if not p2_info:
            raise ValueError(f"Unknown chain target platform: {p2}")

        p2_limit = p2_info.char_limit
        input_data = resp_1
        
        # If response length + query length is close to limit, we summarize
        if len(resp_1) + len(query) + 200 > p2_limit:
            logger.warning(f"Response from {p1} ({len(resp_1)} chars) plus query exceeds limit for {p2} ({p2_limit} chars). Summarizing...")
            input_data = await self.summarize_response(resp_1, p2_limit - len(query) - 500)

        # Step 3: Execute Platform 2
        chain_instruction = f"Below is output from {p1.upper()} to be analyzed/processed:\n\n{input_data}\n\nTask: {query}"
        logger.info(f"Chain Step 2: Querying {p2} with outputs from {p1}...")
        
        # In Step 2, we do not need the original context sources since they are already built into p1's response.
        resp_2 = await self.orchestrator.ask_ai(p2, chain_instruction, None)
        return resp_2
