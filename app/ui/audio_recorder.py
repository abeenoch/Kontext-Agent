import sys
import asyncio
import websockets
import json
import base64
import sounddevice as sd
import numpy as np
from datetime import datetime
import queue
import signal
import os

# Configuration
BACKEND_WS_URL = os.getenv("BACKEND_WS_URL", "ws://localhost:8000/ws/meeting")
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.5  # 500ms

# Global state
audio_queue = queue.Queue()
recording = True


def audio_callback(indata, frames, time_info, status):
    """Audio capture callback."""
    global recording
    if status:
        print(f"Audio status: {status}")
    
    if recording:
        audio_int16 = (indata[:, 0] * 32767).astype(np.int16)
        try:
            audio_queue.put_nowait(audio_int16.tobytes())
        except queue.Full:
            pass  # Skip if queue is full


async def send_audio_to_backend(meeting_id: str):
    """Send audio chunks via WebSocket."""
    global recording
    uri = BACKEND_WS_URL
    chunk_index = 0
    
    try:
        async with websockets.connect(uri) as websocket:
            print(f"[Recorder] WebSocket connected for meeting {meeting_id}")
            
            # Send START message
            await websocket.send(json.dumps({
                "type": "START",
                "metadata": {
                    "title": "Recording",  
                    "participants": []
                }
            }))
            
            # Wait for confirmation
            response = await websocket.recv()
            data = json.loads(response)
            if data["type"] == "MEETING_STARTED":
                print(f"[Recorder] Meeting started: {data['meeting_id']}")
            
            # Send audio chunks
            while recording:
                try:
                    # Get audio from queue
                    audio_bytes = await asyncio.wait_for(
                        asyncio.to_thread(audio_queue.get, timeout=1),
                        timeout=1.5
                    )
                    
                    # Encode to base64
                    audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
                    
                    # Send to server
                    await websocket.send(json.dumps({
                        "type": "AUDIO_CHUNK",
                        "meeting_id": meeting_id,
                        "data": audio_b64,
                        "chunk_index": chunk_index,
                        "timestamp": datetime.now().timestamp()
                    }))
                    
                    chunk_index += 1
                    
                    if chunk_index % 20 == 0:  # Log every 10 seconds
                        print(f"[Recorder] Sent {chunk_index} chunks")
                    
                except asyncio.TimeoutError:
                    # Send heartbeat
                    await websocket.send(json.dumps({
                        "type": "PING",
                        "meeting_id": meeting_id
                    }))
                except Exception as e:
                    print(f"[Recorder] Error sending audio: {e}")
                    break
            
            # Send STOP message
            print(f"[Recorder] Sending STOP message")
            await websocket.send(json.dumps({
                "type": "STOP",
                "meeting_id": meeting_id
            }))
            
            # Wait a bit for server to process
            await asyncio.sleep(2)
            
            print("[Recorder] WebSocket closed normally")
            
    except Exception as e:
        print(f"[Recorder] WebSocket error: {e}")


def signal_handler(signum, frame):
    """Handle termination signal."""
    global recording
    print("\n[Recorder] Stopping recording...")
    recording = False


def main():
    """Main entry point."""
    global recording
    
    if len(sys.argv) < 2:
        print("Usage: python audio_recorder.py <meeting_id>")
        sys.exit(1)
    
    meeting_id = sys.argv[1]
    print(f"[Recorder] Starting audio recorder for meeting: {meeting_id}")
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start audio stream
    print(f"[Recorder] Starting audio stream...")
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        callback=audio_callback,
        blocksize=int(SAMPLE_RATE * CHUNK_DURATION)
    )
    
    try:
        with stream:
            print(f"[Recorder] Audio stream started. Recording...")
            
            # Run WebSocket in async loop
            asyncio.run(send_audio_to_backend(meeting_id))
            
    except KeyboardInterrupt:
        print("\n[Recorder] Interrupted by user")
    except Exception as e:
        print(f"[Recorder] Error: {e}")
    finally:
        recording = False
        print("[Recorder] Stopped")


if __name__ == "__main__":
    main()