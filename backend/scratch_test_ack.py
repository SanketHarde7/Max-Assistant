import asyncio
from modules.llm import get_acknowledgment

async def main():
    texts = [
        "search for python",
        "open youtube",
        "play some music",
        "turn on the fan",
        "schedule a meeting",
        "what is the time"
    ]
    for t in texts:
        ack = await get_acknowledgment(t)
        print(f"'{t}' -> '{ack}'")

if __name__ == "__main__":
    asyncio.run(main())
