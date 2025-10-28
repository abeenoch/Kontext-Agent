from fastapi import APIRouter, WebSocket,  WebSocketDisconnect
from app.services.voice_agent import transcribe_audio, speak
from app.services.voice_stream import handle_voice_stream
from app.services.llm_agent import query_llm
from fastapi.responses import HTMLResponse



router = APIRouter(prefix="/voice", tags=["voice"])

@router.post("/chat")
async def voice_chat():
    user_text = transcribe_audio()
    llm_resp = query_llm(user_text)
    speak(llm_resp)
    return {"user_text": user_text, "assistant_text": llm_resp}

from fastapi import APIRouter, WebSocket
from app.services.voice_stream import handle_voice_stream

router = APIRouter(prefix="/voice", tags=["voice"])

@router.websocket("/stream_chat")
async def stream_chat(websocket: WebSocket):
    await websocket.accept()
    print("Client connected for streaming")

    try:
        while True:
            message = await websocket.receive()
            
            if "bytes" in message:  # <-- handle audio chunk
                audio_chunk = message["bytes"]
                print(f"Received audio chunk ({len(audio_chunk)} bytes)")
                await websocket.send_text(f"🎤 Got {len(audio_chunk)} bytes of audio")

            elif "text" in message:
                print(f"Text message: {message['text']}")
                await websocket.send_text(f"Echo: {message['text']}")
    except WebSocketDisconnect:
        print("Client disconnected")


@router.get("/stream_test_ui", response_class=HTMLResponse)
async def stream_test_ui():
    """Simple browser client to test real-time voice streaming."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Voice Stream Test</title>
    </head>
    <body>
        <h2>🎙️ Kontext Agent Voice Stream Test</h2>
        <button id="startBtn">Start Streaming</button>
        <button id="stopBtn">Stop</button>
        <pre id="output"></pre>

        <script>
        let ws;
        let mediaRecorder;

        document.getElementById('startBtn').onclick = async () => {
            const output = document.getElementById('output');
            output.textContent = "Connecting...\n";
            ws = new WebSocket("ws://127.0.0.1:8080/voice/stream_chat");

            ws.onopen = async () => {
                output.textContent += "Connected! Recording audio...\n";
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });

                mediaRecorder.addEventListener('dataavailable', async (e) => {
                    if (e.data.size > 0 && ws.readyState === WebSocket.OPEN) {
                        const arrayBuffer = await e.data.arrayBuffer();
                        ws.send(arrayBuffer);  // send audio chunk
                    }
                });
                mediaRecorder.start(250); // send every 250ms
            };

            ws.onmessage = (event) => {
                output.textContent += event.data + "\\n";
            };
        };

        document.getElementById('stopBtn').onclick = () => {
            mediaRecorder?.stop();
            ws?.close();
            document.getElementById('output').textContent += "\\nStopped.";
        };
        </script>
    </body>
    </html>
    """
