from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import os, asyncio, base64, tempfile, time

from app.services.voice_stream import transcribe_audio_stream, generate_llm_reply
from app.services.summarizer import summarize_periodically

router = APIRouter(prefix="/meeting", tags=["Meeting Recorder"])
TRANSCRIPTS_DIR = "data/meeting_transcripts"
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)


@router.websocket("/stream")
async def meeting_stream(websocket: WebSocket):
    await websocket.accept()
    session_id = os.urandom(8).hex()
    print(f"Meeting stream started → {session_id}")

    transcript_path = os.path.join(TRANSCRIPTS_DIR, f"transcript_{session_id}.txt")

    # launch background 10-min summary task
    summary_task = asyncio.create_task(summarize_periodically(transcript_path, websocket))

    try:
        while True:
            data = await websocket.receive_text()
            if data == "STOP":
                print("Stop received — closing meeting stream.")
                break

            try:
                user_text = await transcribe_audio_stream(data)
                if user_text:
                    with open(transcript_path, "a", encoding="utf-8") as f:
                        f.write(user_text + "\n")

                    await websocket.send_json({
                        "type": "transcript_update",
                        "text": user_text
                    })
            except Exception as e:
                print(f"Meeting chunk error: {e}")

        # final summary
        with open(transcript_path, "r", encoding="utf-8") as f:
            full_text = f.read()

        final_prompt = (
            "Summarize this entire meeting in detail with sections: "
            "1) Overview, 2) Key Points, 3) Decisions, 4) Action Items.\n\n"
            f"{full_text}"
        )
        final_summary = await generate_llm_reply(final_prompt)
        await websocket.send_json({
            "type": "final_summary",
             "content": final_summary
        })

    except WebSocketDisconnect:
        print(f"Client disconnected: {session_id}")

    finally:
        summary_task.cancel()
        if websocket.client_state.name != "DISCONNECTED":
            try:
                await websocket.close()
            except:
                pass
        print(f"Meeting stream closed → {session_id}")




@router.get("/ui", response_class=HTMLResponse)
async def meeting_ui():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🎙️ Kontext Meeting</title>
    </head>
    <body style="font-family:sans-serif;padding:20px;">
        <h2>Kontext Meeting Assistant</h2>
        <button id="startBtn">Start Meeting</button>
        <button id="stopBtn" disabled>Stop Meeting</button>
        <p>Status: <span id="status">Disconnected</span></p>

        <div id="transcripts" style="border:1px solid #ccc;padding:10px;margin-top:10px;width:80%;height:200px;overflow-y:auto;"></div>
        <div id="summaries" style="border:1px solid #ccc;padding:10px;margin-top:10px;width:80%;height:200px;overflow-y:auto;"></div>

        <script>
            let ws, mediaRecorder, chunks = [], sendTimer = null;

            document.getElementById("startBtn").onclick = async () => {
                ws = new WebSocket("ws://127.0.0.1:8080/meeting/stream");

                ws.onopen = () => {
                    document.getElementById("status").innerText = "Recording 🎙️";
                    document.getElementById("startBtn").disabled = true;
                    document.getElementById("stopBtn").disabled = false;
                    console.log("✅ WebSocket connected");
                };

                ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        if (data.type === "transcript_update") {
                            const div = document.createElement("div");
                            div.textContent = data.text;
                            document.getElementById("transcripts").appendChild(div);
                        } else if (data.type === "summary_update") {
                            const div = document.createElement("div");
                            div.innerHTML = `<b>${data.timestamp}</b>: ${data.summary}`;
                            document.getElementById("summaries").appendChild(div);
                        } else if (data.type === "final_summary") {
                            const div = document.createElement("div");
                            div.innerHTML = `<h3>🧠 Final Summary</h3><p>${data.content}</p>`;
                            document.getElementById("summaries").appendChild(div);
                        } else {
                            console.log("🗨️", event.data);
                        }
                    } catch (err) {
                        console.warn("Non-JSON message:", event.data);
                    }
                };

                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });

                // collect chunks
                mediaRecorder.ondataavailable = e => {
                    if (e.data.size > 0) chunks.push(e.data);
                };

                // periodically send combined valid .webm blobs (every 10s)
                sendTimer = setInterval(async () => {
                    if (chunks.length > 0 && ws.readyState === WebSocket.OPEN) {
                        const blob = new Blob(chunks, { type: "audio/webm" });
                        const buffer = await blob.arrayBuffer();
                        const base64 = arrayBufferToBase64(buffer);
                        ws.send(base64);
                        chunks = []; // reset buffer
                        console.log("📤 Sent 10s audio chunk");
                    }
                }, 10000);

                mediaRecorder.start();
            };

            document.getElementById("stopBtn").onclick = async () => {
                clearInterval(sendTimer);
                mediaRecorder.stop();

                // wait for final chunk flush
                setTimeout(async () => {
                    if (chunks.length > 0 && ws.readyState === WebSocket.OPEN) {
                        const blob = new Blob(chunks, { type: "audio/webm" });
                        const buffer = await blob.arrayBuffer();
                        const base64 = arrayBufferToBase64(buffer);
                        ws.send(base64);
                    }
                    ws.send("STOP");
                    ws.close();
                }, 1000);

                document.getElementById("status").innerText = "Stopped 🛑";
                document.getElementById("startBtn").disabled = false;
                document.getElementById("stopBtn").disabled = true;
            };

            function arrayBufferToBase64(buffer) {
                let binary = '';
                const bytes = new Uint8Array(buffer);
                for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
                return btoa(binary);
            }
        </script>
    </body>
    </html>
    """
