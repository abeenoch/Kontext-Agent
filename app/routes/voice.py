from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from app.services.voice_stream import (
    transcribe_audio_stream,
    generate_llm_reply,
    synthesize_speech
)
import asyncio

router = APIRouter(prefix="/voice", tags=["Voice Streaming"])


@router.websocket("/live_chat")
async def live_chat(websocket: WebSocket):
    await websocket.accept()
    print("Voice chat session started")

    try:
        while True:
            data = await websocket.receive_text()
            if data == "STOP":
                await websocket.send_text("Conversation ended.")
                break

            print(f"Received {len(data)} base64 chars from client")

            user_text = await transcribe_audio_stream(data)
            print(f"Transcribed: {user_text}")

            llm_reply = await generate_llm_reply(user_text)
            print(f"LLM reply: {llm_reply}")

            audio_b64 = await synthesize_speech(llm_reply)

            await websocket.send_json({
                "user_text": user_text,
                "assistant_text": llm_reply,
                "audio_base64": audio_b64
            })

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error in live chat: {e}")
        await websocket.send_text(f"Error: {str(e)}")



@router.get("/live_chat_ui", response_class=HTMLResponse)
async def live_chat_ui():
    """
    Buffered voice chat UI — records once, sends the full clip when stopped.
    Prevents multiple partial transcriptions and overlapping replies.
    """
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🎤 Buffered Voice Chat</title>
    </head>
    <body style="font-family: sans-serif; padding: 20px;">
        <h2>🎙️ Buffered Voice Chat with LLM</h2>
        <button id="startBtn">Start Recording</button>
        <button id="stopBtn" disabled>Stop Recording</button>
        <p>Status: <span id="status">Disconnected</span></p>
        <p><b>User:</b> <span id="userText"></span></p>
        <p><b>Assistant:</b> <span id="assistantText"></span></p>
        <audio id="audioPlayer" controls autoplay></audio>

        <script>
            let ws;
            let mediaRecorder;
            let chunks = [];

            document.getElementById("startBtn").onclick = async () => {
                ws = new WebSocket("ws://127.0.0.1:8080/voice/live_chat");

                ws.onopen = () => {
                    document.getElementById("status").innerText = "Connected 🎧";
                    document.getElementById("startBtn").disabled = true;
                    document.getElementById("stopBtn").disabled = false;
                    console.log("✅ WebSocket connected");
                };

                ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        if (data.user_text)
                            document.getElementById("userText").innerText = data.user_text;
                        if (data.assistant_text)
                            document.getElementById("assistantText").innerText = data.assistant_text;
                        if (data.audio_base64) {
                            const audioBlob = base64ToBlob(data.audio_base64, "audio/wav");
                            const url = URL.createObjectURL(audioBlob);
                            const audioPlayer = document.getElementById("audioPlayer");
                            audioPlayer.src = url;
                            audioPlayer.play();
                        }
                    } catch (e) {
                        console.log("Non-JSON message:", event.data);
                    }
                };

                ws.onclose = () => {
                    document.getElementById("status").innerText = "Disconnected";
                    document.getElementById("startBtn").disabled = false;
                    document.getElementById("stopBtn").disabled = true;
                    console.log("🔌 WebSocket closed");
                };

                // 🎙️ Start microphone recording
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
                chunks = [];

                mediaRecorder.ondataavailable = (event) => {
                    chunks.push(event.data);
                };

                mediaRecorder.start();
                console.log("🎙️ Recording started");
            };

            document.getElementById("stopBtn").onclick = async () => {
                console.log("🛑 Stopping recording...");
                mediaRecorder.stop();

                mediaRecorder.onstop = async () => {
                    console.log("📤 Sending full audio clip...");
                    const fullBlob = new Blob(chunks, { type: "audio/webm" });
                    const arrayBuffer = await fullBlob.arrayBuffer();
                    const base64Data = arrayBufferToBase64(arrayBuffer);
                    ws.send(base64Data); // Send full audio
                    ws.send("STOP");     // Signal end of user speech
                    chunks = [];
                };

                document.getElementById("status").innerText = "Stopped 🛑";
                document.getElementById("startBtn").disabled = false;
                document.getElementById("stopBtn").disabled = true;
            };

            function arrayBufferToBase64(buffer) {
                let binary = '';
                const bytes = new Uint8Array(buffer);
                const chunkSize = 0x8000;
                for (let i = 0; i < bytes.length; i += chunkSize) {
                    const chunk = bytes.subarray(i, i + chunkSize);
                    binary += String.fromCharCode.apply(null, chunk);
                }
                return btoa(binary);
            }

            function base64ToBlob(base64, mime) {
                const byteChars = atob(base64);
                const byteNumbers = new Array(byteChars.length);
                for (let i = 0; i < byteChars.length; i++) {
                    byteNumbers[i] = byteChars.charCodeAt(i);
                }
                const byteArray = new Uint8Array(byteNumbers);
                return new Blob([byteArray], { type: mime });
            }
        </script>
    </body>
    </html>
    """
