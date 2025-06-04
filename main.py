import os
import math
import threading
import asyncio
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydub import AudioSegment
import uvicorn
import io
from typing import AsyncGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Radio Stream API",
    description="Dedicated API for streaming audio continuously",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for streaming
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Path to your audio file
AUDIO_FILE_PATH = "/audio.mp3"

# Global variables for the audio stream
_audio_bytes = None
_audio_prepared = False
_preparation_lock = threading.Lock()

def prepare_audio_in_thread():
    """Prepare the audio file in a separate thread"""
    global _audio_bytes, _audio_prepared
    
    try:
        with _preparation_lock:
            if _audio_prepared:
                return
                
            logger.info("Preparing audio for streaming...")
            
            if not os.path.exists(AUDIO_FILE_PATH):
                logger.error("Audio file not found")
                return
            
            # Load the audio file
            audio = AudioSegment.from_mp3(AUDIO_FILE_PATH)
            
            # Get duration in minutes
            duration_ms = len(audio)
            duration_minutes = duration_ms / (1000 * 60)
            
            logger.info(f"Original audio duration: {duration_minutes:.2f} minutes")
            
            # Calculate target duration (ceiling to next integer minute)
            target_minutes = math.ceil(duration_minutes)
            target_duration_ms = target_minutes * 60 * 1000
            
            logger.info(f"Target duration: {target_minutes} minutes")
            
            # Add silence padding if needed
            if duration_ms < target_duration_ms:
                silence_duration_ms = target_duration_ms - duration_ms
                logger.info(f"Adding {silence_duration_ms/1000:.2f} seconds of silence")
                silence = AudioSegment.silent(duration=silence_duration_ms)
                padded_audio = audio + silence
            else:
                padded_audio = audio
                logger.info("No padding needed")
            
            # Convert to bytes
            audio_buffer = io.BytesIO()
            padded_audio.export(audio_buffer, format="mp3")
            _audio_bytes = audio_buffer.getvalue()
            _audio_prepared = True
            
            logger.info(f"Audio prepared successfully: {len(_audio_bytes)} bytes")
            
    except Exception as e:
        logger.error(f"Error preparing audio: {e}")

# Start preparing audio in background when module loads
threading.Thread(target=prepare_audio_in_thread, daemon=True).start()

async def audio_stream_generator() -> AsyncGenerator[bytes, None]:
    """Generator that yields audio data in chunks, repeating indefinitely"""
    global _audio_bytes, _audio_prepared
    
    # Wait for audio to be prepared
    max_wait = 30  # 30 seconds max wait
    wait_time = 0
    while not _audio_prepared and wait_time < max_wait:
        await asyncio.sleep(0.5)
        wait_time += 0.5
    
    if not _audio_prepared or _audio_bytes is None:
        raise HTTPException(status_code=500, detail="Audio preparation failed")
    
    logger.info(f"Starting audio stream with {len(_audio_bytes)} bytes")
    
    try:
        chunk_size = 8192  # 8KB chunks
        loop_count = 0
        
        while True:  # Infinite loop for continuous streaming
            loop_count += 1
            logger.debug(f"Starting audio loop #{loop_count}")
            
            # Stream the audio in chunks
            for i in range(0, len(_audio_bytes), chunk_size):
                chunk = _audio_bytes[i:i + chunk_size]
                yield chunk
                # Small delay to control streaming rate
                await asyncio.sleep(0.02)  # 20ms delay between chunks
            
            logger.debug(f"Audio loop #{loop_count} completed, restarting...")
            # Small pause between loops
            await asyncio.sleep(0.1)
            
    except asyncio.CancelledError:
        logger.info("Audio stream cancelled by client")
        raise
    except Exception as e:
        logger.error(f"Error in audio stream generator: {e}")
        raise

@app.get("/stream")
async def stream_audio():
    """
    Stream audio continuously, repeating the padded audio file indefinitely.
    This simulates a live radio stream.
    """
    try:
        logger.info("Client requesting audio stream")
        
        return StreamingResponse(
            audio_stream_generator(),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=radio_stream.mp3",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Accept-Ranges": "none",
                "Connection": "keep-alive",
                "Transfer-Encoding": "chunked"
            }
        )
        
    except Exception as e:
        logger.error(f"Error starting audio stream: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start audio stream: {str(e)}")

@app.get("/info")
async def get_audio_info():
    """Get information about the audio file."""
    try:
        if not os.path.exists(AUDIO_FILE_PATH):
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        audio = AudioSegment.from_mp3(AUDIO_FILE_PATH)
        duration_minutes = len(audio) / (1000 * 60)
        target_minutes = math.ceil(duration_minutes)
        
        return {
            "file_path": AUDIO_FILE_PATH,
            "original_duration_minutes": round(duration_minutes, 2),
            "target_duration_minutes": target_minutes,
            "padding_needed_seconds": round((target_minutes * 60) - (len(audio) / 1000), 2),
            "file_size_mb": round(os.path.getsize(AUDIO_FILE_PATH) / (1024 * 1024), 2),
            "streaming_mode": "continuous_loop",
            "description": "Audio streams continuously with seamless looping",
            "prepared": _audio_prepared,
            "buffer_size_bytes": len(_audio_bytes) if _audio_bytes else 0
        }
        
    except Exception as e:
        logger.error(f"Error getting audio info: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get audio info: {str(e)}")

@app.get("/")
def read_root():
    return {"message": "Radio Stream API", "port": 8005, "endpoints": ["/stream", "/info"]}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8005))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"🎵 Starting stream server on {host}:{port}")
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )
