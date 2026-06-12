import asyncio
from agent_core import get_agent

async def test_ghost_mode():
    agent = get_agent()
    print("Agent created.")
    
    # 1. Try to activate
    res = await agent.process_text_input("activate ghost mode", use_tts=False)
    print(f"Activation result: {res}")
    
    # 2. Try to type something
    res = await agent.process_text_input("hello world", use_tts=False)
    print(f"Typing result: {res}")
    
    # 3. Try to press enter
    res = await agent.process_text_input("press enter", use_tts=False)
    print(f"Enter result: {res}")

if __name__ == "__main__":
    asyncio.run(test_ghost_mode())
