import os
import asyncio
import base64
import tempfile
import time
import re
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import os, asyncio, base64, tempfile

from app.services.voice_stream import transcribe_audio_stream, generate_llm_reply
from app.services.summarizer import summarize_periodically
from app.services.meeting_agent import agent_chat

router = APIRouter(prefix="/meeting", tags=["Meeting Recorder"])

TRANSCRIPTS_DIR = "data/meeting_transcripts"
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)


@router.websocket("/stream")
async def meeting_stream(websocket: WebSocket):
    meeting_id = websocket.query_params.get("meeting_id")
    session_id = meeting_id or os.urandom(8).hex()

    await websocket.accept()
    print(f"Meeting stream started → {session_id}")

    transcript_path = os.path.join(TRANSCRIPTS_DIR, f"transcript_{session_id}.txt")
    summary_path = os.path.join(TRANSCRIPTS_DIR, f"summary_{session_id}.txt")

    summary_task = asyncio.create_task(summarize_periodically(transcript_path, websocket))
    meeting_active = True
    final_summary = None

    try:
        while True:
            data = await websocket.receive_text()

            #  STOP MEETING
            if data == "STOP":
                print(f"Stop received — meeting phase ended (session={session_id})")
                meeting_active = False

                await websocket.send_json({
                    "type": "status",
                    "content": "Meeting stopped, you can still chat."
                })

                if os.path.exists(transcript_path):
                    with open(transcript_path, "r", encoding="utf-8") as f:
                        full_text = f.read().strip()

                    if not full_text:
                        await websocket.send_json({
                            "type": "error",
                            "content": "Transcript is empty, skipping summary."
                        })
                        continue

                    # Build a structured prompt for a detailed summary
                    final_prompt = (
                        "You are an expert meeting summarizer.\n"
                        "Write a full, well-structured summary based on the transcript below.\n\n"
                        "Include these sections:\n"
                        "1. **Overview** – context and goals of the meeting.\n"
                        "2. **Key Points** – main topics discussed.\n"
                        "3. **Decisions** – conclusions or agreements.\n"
                        "4. **Action Items** – follow-ups or next steps.\n\n"
                        "Transcript:\n"
                        f"{full_text}\n\n"
                        "Now produce the complete summary in Markdown format."
                    )

                    try:
                        final_summary = await generate_llm_reply(final_prompt)
                        final_summary = final_summary.strip()
                    except Exception as e:
                        print(f"[ERROR] Summarization failed: {e}")
                        final_summary = "Summary generation failed."

                    # Retry if model output looks incomplete
                    if len(final_summary.split()) < 25 or "Overview" == final_summary.strip():
                        print("[WARN] Summary seems incomplete — retrying...")
                        final_summary = await generate_llm_reply(final_prompt)
                        final_summary = final_summary.strip()

                    # Save full summary to disk
                    with open(summary_path, "w", encoding="utf-8") as f:
                        f.write(final_summary)

                    await websocket.send_json({
                        "type": "final_summary",
                        "content": final_summary
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Transcript not found for final summary."
                    })

                continue

            #  HANDLE CHAT
            if data.startswith("CHAT:"):
                message = data.replace("CHAT:", "").strip()

                # Prefer final summary as chat context
                if os.path.exists(summary_path):
                    with open(summary_path, "r", encoding="utf-8") as f:
                        context_text = f.read()
                elif os.path.exists(transcript_path):
                    with open(transcript_path, "r", encoding="utf-8") as f:
                        context_text = f.read()
                else:
                    await websocket.send_json({
                        "type": "error",
                        "content": "No meeting context available for chat."
                    })
                    continue

                agent_reply = await agent_chat(message, context_text)
                await websocket.send_json({
                    "type": "agent_reply",
                    "content": agent_reply
                })
                continue

            #AUDIO CHUNKS 
            if meeting_active:
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
                    print(f"[ERROR] Audio processing failed: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "content": str(e)
                    })
            else:
                await websocket.send_json({
                    "type": "warning",
                    "content": "Meeting has ended. Use CHAT: to talk to the agent."
                })

    except WebSocketDisconnect:
        print(f"Client disconnected: {session_id}")

    finally:
        summary_task.cancel()
        if websocket.client_state.name != "DISCONNECTED":
            try:
                await websocket.close()
            except Exception:
                pass
        print(f"Meeting stream closed → {session_id}")




@router.get("/ui", response_class=HTMLResponse)
async def meeting_ui():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Kontext Meeting</title>
        <style>
            body { font-family: sans-serif; padding: 20px; background: #fafafa; }
            button { padding: 8px 14px; margin: 4px; border-radius: 6px; border: none; background: #0078D7; color: white; cursor: pointer; }
            button:disabled { background: #ccc; cursor: not-allowed; }
            input { padding: 8px; margin-top: 6px; border: 1px solid #ccc; border-radius: 4px; width: 70%; }
            #transcripts, #summaries, #agentReplies {
                border: 1px solid #ccc; padding: 10px; margin-top: 10px;
                width: 80%; height: 200px; overflow-y: auto; background: white;
            }
        </style>
    </head>
    <body>
        <h2>Kontext Meeting Assistant</h2>
        <button id="startBtn">Start Meeting</button>
        <button id="stopBtn" disabled>Stop Meeting</button>
        <p>Status: <span id="status">Disconnected</span></p>

        <h3>Live Transcripts</h3>
        <div id="transcripts"></div>

        <h3>Summaries</h3>
        <div id="summaries"></div>

        <hr>
        <h3>Ask Kontext Agent / Post-Meeting Commands</h3>
        <input id="chatInput" placeholder="e.g. Send meeting summary to john@pivot.co or Push summary to Notion" />
        <button id="sendBtn">Send</button>

        <div id="agentReplies"></div>

        <script>
            let ws, meetingId = null, mediaRecorder, chunks = [], sendTimer = null, finalSummary = '';

            async function connectWebSocket(existingId = null) {
                return new Promise((resolve, reject) => {
                    meetingId = existingId || meetingId || crypto.randomUUID();
                    const url = `ws://127.0.0.1:8080/meeting/stream?meeting_id=${meetingId}`;
                    console.log("Connecting WebSocket:", url);
                    const socket = new WebSocket(url);

                    socket.onopen = () => {
                        console.log("WebSocket connected:", meetingId);
                        document.getElementById("status").innerText = "Connected";
                        resolve(socket);
                    };

                    socket.onerror = (err) => {
                        console.error("WebSocket error", err);
                        document.getElementById("status").innerText = "Connection error";
                        reject(err);
                    };
                });
            }

            document.getElementById("startBtn").onclick = async () => {
                ws = await connectWebSocket();

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
                            finalSummary = data.content;
                            const div = document.createElement("div");
                            div.innerHTML = `<h3>Final Summary</h3><p>${finalSummary}</p>`;
                            document.getElementById("summaries").appendChild(div);
                            document.getElementById("status").innerText = "Meeting complete";
                        } else if (data.type === "agent_reply") {
                            const div = document.createElement("div");
                            div.innerHTML = `<i>${data.content}</i>`;
                            document.getElementById("agentReplies").appendChild(div);
                        }
                    } catch (err) {
                        console.warn("Non-JSON message:", event.data);
                    }
                };

                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });

                mediaRecorder.ondataavailable = e => {
                    if (e.data.size > 0) chunks.push(e.data);
                };

                sendTimer = setInterval(async () => {
                    if (chunks.length > 0 && ws.readyState === WebSocket.OPEN) {
                        const blob = new Blob(chunks, { type: "audio/webm" });
                        const buffer = await blob.arrayBuffer();
                        ws.send(arrayBufferToBase64(buffer));
                        chunks = [];
                        console.log("Sent 10s audio chunk");
                    }
                }, 10000);

                mediaRecorder.start();
                document.getElementById("startBtn").disabled = true;
                document.getElementById("stopBtn").disabled = false;
                document.getElementById("status").innerText = "Recording...";
            };

            document.getElementById("stopBtn").onclick = async () => {
                clearInterval(sendTimer);
                mediaRecorder.stop();

                setTimeout(async () => {
                    if (chunks.length > 0 && ws.readyState === WebSocket.OPEN) {
                        const blob = new Blob(chunks, { type: "audio/webm" });
                        const buffer = await blob.arrayBuffer();
                        ws.send(arrayBufferToBase64(buffer));
                    }
                    ws.send("STOP");
                }, 1000);

                document.getElementById("status").innerText = "Stopped (you can still chat)";
                document.getElementById("startBtn").disabled = false;
                document.getElementById("stopBtn").disabled = true;
            };

            document.getElementById("sendBtn").onclick = async () => {
                const val = document.getElementById("chatInput").value.trim();
                if (!val) return;

                // Reconnect with same meeting ID if disconnected
                if (!ws || ws.readyState !== WebSocket.OPEN) {
                    console.log("Reconnecting WebSocket for chat...");
                    ws = await connectWebSocket(meetingId);

                    ws.onmessage = (event) => {
                        try {
                            const data = JSON.parse(event.data);
                            if (data.type === "agent_reply") {
                                const div = document.createElement("div");
                                div.innerHTML = `<i>${data.content}</i>`;
                                document.getElementById("agentReplies").appendChild(div);
                            }
                        } catch (err) {
                            console.warn("Non-JSON message:", event.data);
                        }
                    };
                }

                ws.send("CHAT:" + val);
                const div = document.createElement("div");
                div.textContent = "You: " + val;
                document.getElementById("agentReplies").appendChild(div);
                document.getElementById("chatInput").value = '';
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





