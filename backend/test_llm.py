import asyncio
import sys
from modules.llm import get_response
from config import config

async def test():
    res = await get_response("open youtube and open notepad")
    print(res)

if __name__ == "__main__":
    asyncio.run(test())
