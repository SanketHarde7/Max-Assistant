import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://localhost:8000/ws"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to WebSocket")
            
            # Send a request that should trigger an acknowledgment
            req = {
                "type": "text",
                "text": "Please search for the history of Python programming language"
            }
            await websocket.send(json.dumps(req))
            
            while True:
                response = await websocket.recv()
                data = json.loads(response)
                event = data.get("event")
                text = data.get("text", "")
                print(f"Received event: {event}, text: {text[:50]}")
                
                if event == "audio_response" and not data.get("audio"):
                    print("Received empty audio response")
                elif event == "audio_response":
                    print("Received audio response with data")
                    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
