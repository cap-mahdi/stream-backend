import asyncio
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

AUDIO_FILE = "audio.mp3"
CHUNK_SIZE = 4096
CHUNK_DELAY = 0.1  # Simulates real-time audio rate

listeners = []  # Each listener is an asyncio.Queue
current_chunk = None  # Shared current chunk for synchronization

async def broadcast_audio():
    global current_chunk
    while True:
        with open(AUDIO_FILE, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                current_chunk = chunk
                # Create a list of tasks to send chunk to all listeners simultaneously
                tasks = []
                for q in listeners:
                    try:
                        tasks.append(q.put_nowait(chunk))
                    except asyncio.QueueFull:
                        # Skip if queue is full to prevent blocking
                        continue
                
                await asyncio.sleep(CHUNK_DELAY)
        # Loop the audio like a radio
        print("Looping audio file")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(broadcast_audio())

async def audio_stream():
    q = asyncio.Queue(maxsize=10)  # Limit queue size to prevent memory issues
    listeners.append(q)
    
    # Send current chunk immediately to sync new listeners
    if current_chunk:
        try:
            q.put_nowait(current_chunk)
        except asyncio.QueueFull:
            pass
    
    try:
        while True:
            chunk = await q.get()
            yield chunk
    finally:
        if q in listeners:
            listeners.remove(q)

@app.get("/radio")
async def get_radio():
    headers = {
        "Content-Type": "audio/mpeg",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive"
    }
    return StreamingResponse(audio_stream(), headers=headers)