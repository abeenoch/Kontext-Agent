import asyncio
import json
import base64
import logging
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from typing import Optional

from app.config import settings
from app.database import db
from app.core.audio_processor import AudioBuffer, AudioValidator
from app.core.transcriber import transcriber
from app.core.summarizer import summarizer
from app.core.rag_engine import rag_engine
from app.services.streaming_transcriber import streaming_transcriber

logger = logging.getLogger(__name__)


class MeetingWebSocketHandler:
    """Handles WebSocket connection for a single meeting."""
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.meeting_id: Optional[str] = None
        self.meeting_active = False
        self.audio_buffer = AudioBuffer()
        self.validator = AudioValidator()
        
        # Background tasks
        self.transcription_task: Optional[asyncio.Task] = None
        self.summarization_task: Optional[asyncio.Task] = None
    
    async def handle(self):
        """Main WebSocket handler loop."""
        await self.websocket.accept()
        logger.info("WebSocket connection accepted")
        
        try:
            async for message in self.websocket.iter_text():
                await self._process_message(message)
            
            # Connection closed by client
            logger.info(f"Client closed WebSocket for meeting {self.meeting_id}")
                
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for meeting {self.meeting_id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}", exc_info=True)
            await self._send_error(str(e))
        finally:
            # Only cleanup if meeting wasn't properly stopped
            if self.meeting_active:
                await self._emergency_cleanup()
            logger.info(f"WebSocket handler exited for meeting {self.meeting_id}")
    
    async def _process_message(self, message: str):
        """Process incoming WebSocket message."""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "START":
                await self._handle_start(data)
            elif msg_type == "AUDIO_CHUNK":  # Backward compatibility (batch mode)
                await self._handle_audio_chunk(data)
            elif msg_type == "AUDIO_FRAME":  # Streaming mode
                await self._handle_audio_frame(data)
            elif msg_type == "PING":
                await self._handle_ping()
            elif msg_type == "STOP":
                await self._handle_stop()
            elif msg_type == "CHAT":
                await self._handle_chat(data)
            else:
                logger.warning(f"Unknown message type: {msg_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            await self._send_error("Invalid JSON message")
        except Exception as e:
            logger.error(f"Message processing error: {e}", exc_info=True)
            await self._send_error(str(e))
    
    async def _handle_start(self, data: dict):
        """Handle START message - initialize meeting."""
        metadata = data.get("metadata", {})
        title = metadata.get("title", "Untitled Meeting")
        participants = metadata.get("participants", [])
        
        # Generate meeting ID
        self.meeting_id = f"meeting-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        self.meeting_active = True
        
        # Save to database
        await db.create_meeting(self.meeting_id, title, participants)
        
        # Start background tasks
        self.transcription_task = asyncio.create_task(self._transcription_worker())
        self.summarization_task = asyncio.create_task(self._summarization_worker())
        
        # Send confirmation
        await self.websocket.send_json({
            "type": "MEETING_STARTED",
            "meeting_id": self.meeting_id,
            "status": "recording"
        })
        
        logger.info(f"Started meeting {self.meeting_id}: {title}")
    
    async def _handle_audio_chunk(self, data: dict):
        """Handle AUDIO_CHUNK message - add to buffer."""
        if not self.meeting_active:
            return
        
        try:
            # Decode base64 audio
            audio_b64 = data.get("data", "")
            audio_bytes = base64.b64decode(audio_b64)
            
            # DEBUG: Log audio amplitude to detect if audio is too quiet
            if len(audio_bytes) >= 2:
                import numpy as np
                audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                max_amp = np.max(np.abs(audio_np)) if len(audio_np) > 0 else 0
                if max_amp > 0:
                    logger.debug(f"Audio chunk amplitude: {max_amp:.4f} (quieter than 0.1 = TOO QUIET)")
            
            # Validate chunk
            if not self.validator.validate_pcm_chunk(audio_bytes, settings.chunk_size_bytes):
                logger.warning("Invalid audio chunk received")
                return
            
            # Add to buffer
            self.audio_buffer.add_chunk(audio_bytes)
            
        except Exception as e:
            logger.error(f"Audio chunk processing error: {e}", exc_info=True)
    
    async def _handle_audio_frame(self, data: dict):
        """Handle AUDIO_FRAME message - add to buffer (streaming mode).
        
        Streaming mode sends 10-20ms frames continuously for real-time transcription.
        """
        if not self.meeting_active:
            return
        
        try:
            # Decode base64 audio
            audio_b64 = data.get("data", "")
            audio_bytes = base64.b64decode(audio_b64)
            
            frame_index = data.get("frame_index", -1)
            frame_size_ms = data.get("frame_size_ms", 16)
            
            # DEBUG: Log frame
            if len(audio_bytes) >= 2:
                import numpy as np
                audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                max_amp = np.max(np.abs(audio_np)) if len(audio_np) > 0 else 0
                logger.debug(f"[STREAMING] Frame {frame_index} ({frame_size_ms}ms): {len(audio_bytes)} bytes, max_amp={max_amp:.4f}")
            
            # Validate frame
            if not self.validator.validate_pcm_chunk(audio_bytes):
                logger.warning(f"[STREAMING] Invalid audio frame {frame_index}")
                return
            
            # Add to buffer (same buffer used for both modes)
            self.audio_buffer.add_chunk(audio_bytes)
            
        except Exception as e:
            logger.error(f"[STREAMING] Audio frame processing error: {e}", exc_info=True)
    
    async def _handle_ping(self):
        """Handle PING message - send PONG."""
        await self.websocket.send_json({
            "type": "PONG",
            "meeting_id": self.meeting_id
        })
    
    async def _handle_stop(self):
        """Handle STOP message - finalize meeting PROPERLY."""
        if not self.meeting_active:
            return
        
        logger.info(f"Processing STOP for meeting {self.meeting_id}")
        
        # Mark as inactive to stop accepting new audio
        self.meeting_active = False
        
        # Cancel background tasks FIRST
        if self.transcription_task:
            self.transcription_task.cancel()
            try:
                await self.transcription_task
            except asyncio.CancelledError:
                pass
        
        if self.summarization_task:
            self.summarization_task.cancel()
            try:
                await self.summarization_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Background tasks cancelled, processing remaining audio progressively...")
        
        # Log buffer state at STOP
        total_audio_bytes = len(self.audio_buffer.buffer)
        processed_bytes = self.audio_buffer.processed_offset
        remaining_bytes = total_audio_bytes - processed_bytes
        remaining_secs = remaining_bytes / (settings.SAMPLE_RATE * 2) if remaining_bytes > 0 else 0
        
        logger.info(f"[STOP] Buffer state: total={total_audio_bytes//(settings.SAMPLE_RATE*2)}s, processed={processed_bytes//(settings.SAMPLE_RATE*2)}s, remaining={remaining_secs:.1f}s")
        
        # Process remaining audio PROGRESSIVELY in 60-second chunks (not all at once)
        # This makes the experience feel responsive instead of one long freeze
        chunk_count = 0
        while True:
            result = self.audio_buffer.get_unprocessed_audio()
            if result is None:
                logger.info(f"[STOP] Progressive processing complete: {chunk_count} chunks processed")
                break
            
            audio_np, bytes_processed = result
            
            # Validate before transcribing
            if not self.validator.validate_audio_array(audio_np):
                logger.warning("[STOP] Invalid audio chunk, stopping progressive processing")
                break
            
            chunk_duration = bytes_processed / (settings.SAMPLE_RATE * 2)
            logger.info(f"[STOP] Progressive chunk {chunk_count + 1}: transcribing {chunk_duration:.1f}s")
            
            # Transcribe this chunk
            final_text = await transcriber.transcribe_final(audio_np)
            
            # Mark as processed BEFORE saving (in case of errors)
            self.audio_buffer.mark_processed(bytes_processed)
            
            if final_text:
                await db.add_transcript(self.meeting_id, final_text)
                logger.info(f"[STOP] Chunk {chunk_count + 1}: {len(final_text)} chars")
            else:
                logger.debug(f"[STOP] Chunk {chunk_count + 1}: no speech detected")
            
            chunk_count += 1
        
        # Edge case: process any leftover audio smaller than minimum window
        remaining_audio = self.audio_buffer.get_remaining_audio()
        if remaining_audio is not None and len(remaining_audio) > 0:
            remaining_duration = len(remaining_audio) / settings.SAMPLE_RATE
            logger.info(f"[STOP] Final tail chunk: {remaining_duration:.1f}s")
            
            if self.validator.validate_audio_array(remaining_audio):
                final_text = await transcriber.transcribe_final(remaining_audio)
                if final_text:
                    await db.add_transcript(self.meeting_id, final_text)
                    logger.info(f"[STOP] Final tail: {len(final_text)} chars")
                self.audio_buffer.mark_processed(len(remaining_audio) * 2)  # Convert samples to bytes
        
        # Get complete transcript
        full_transcript = await db.get_full_transcript(self.meeting_id)
        logger.info(f"Full transcript length: {len(full_transcript)} chars")
        
        # Update meeting status to completed
        await db.update_meeting_status(self.meeting_id, "completed", datetime.utcnow())
        logger.info("Meeting status updated to completed")
        
        # Generate final summary ONLY if we have transcript
        if len(full_transcript) > 50:
            logger.info("Generating final summary...")
            try:
                final_summary = await summarizer.summarize_final(full_transcript)
                await db.add_summary(self.meeting_id, final_summary, is_final=True)
                logger.info("Final summary generated and saved")
                
                # Send final summary to client
                await self.websocket.send_json({
                    "type": "FINAL_SUMMARY",
                    "meeting_id": self.meeting_id,
                    "summary": final_summary
                })
                
                # Index to Pinecone (non-blocking, best effort)
                try:
                    await rag_engine.index_meeting(self.meeting_id, full_transcript, final_summary)
                    logger.info("Meeting indexed to RAG")
                except Exception as e:
                    logger.warning(f"RAG indexing failed (non-critical): {e}")
                
            except Exception as e:
                logger.error(f"Failed to generate final summary: {e}", exc_info=True)
                # Still send a response to the client with the error
                await self.websocket.send_json({
                    "type": "FINAL_SUMMARY",
                    "meeting_id": self.meeting_id,
                    "summary": {
                        "overview": f"Summary generation failed: {str(e)[:100]}",
                        "key_points": [],
                        "decisions": [],
                        "action_items": []
                    }
                })
        else:
            logger.warning(f"Transcript too short ({len(full_transcript)} chars), skipping summary")
        
        # Send STOPPED confirmation
        await self.websocket.send_json({
            "type": "MEETING_STOPPED",
            "meeting_id": self.meeting_id,
            "status": "completed"
        })
        
        logger.info(f"Meeting {self.meeting_id} finalized successfully")
        logger.info("WebSocket kept open for post-meeting chat, Notion, and email commands")
    
    async def _handle_chat(self, data: dict):
        """Handle CHAT message - post-meeting Q&A and commands."""
        user_message = data.get("message", "")
        
        if not user_message:
            return
        
        # Save user message
        await db.add_chat_message(self.meeting_id, "user", user_message)
        
        # Check for special commands
        message_lower = user_message.lower()
        
        # EMAIL command: "send summary to email@example.com"
        if any(keyword in message_lower for keyword in ["send", "email", "mail"]):
            await self._handle_email_command(user_message)
            return
        
        # NOTION command: "push to notion" or "send to notion"
        if "notion" in message_lower:
            await self._handle_notion_command()
            return
        
        # Regular chat - use RAG and LLM
        try:
            context = await rag_engine.query_meeting_context(self.meeting_id, user_message)
            if not context:
                context = await db.get_full_transcript(self.meeting_id)
        except Exception as e:
            logger.warning(f"RAG query failed: {e}")
            context = await db.get_full_transcript(self.meeting_id)
        
        # Generate response
        response = await summarizer.answer_question(user_message, context)
        
        # Save assistant message
        await db.add_chat_message(self.meeting_id, "assistant", response)
        
        # Send response
        await self.websocket.send_json({
            "type": "CHAT_RESPONSE",
            "meeting_id": self.meeting_id,
            "message": response
        })
    
    async def _handle_email_command(self, message: str):
        """Handle email sending command."""
        import re
        from app.services.email_service import email_service
        
        # Extract emails from message
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, message)
        
        if not emails:
            response = "I couldn't find any email addresses in your message. Please provide email addresses like: 'Send summary to john@example.com, alice@example.com'"
        else:
            try:
                # Get meeting data
                meeting_data = await db.get_meeting(self.meeting_id)
                if not meeting_data:
                    response = "Meeting not found."
                else:
                    # Get final summary
                    final_summary = await db.get_final_summary(self.meeting_id)
                    if not final_summary:
                        response = "No summary available yet. Please wait for the meeting to finish."
                    else:
                        # Send email
                        success = await email_service.send_summary(
                            meeting_id=self.meeting_id,
                            summary=final_summary,
                            recipients=emails
                        )
                        
                        if success:
                            response = f"Summary sent successfully to: {', '.join(emails)}"
                            await db.log_integration(self.meeting_id, "email", "success", {"recipients": emails})
                        else:
                            response = f"Failed to send email. Please check your SMTP configuration."
                            await db.log_integration(self.meeting_id, "email", "failed", {"recipients": emails})
            
            except Exception as e:
                logger.error(f"Email command failed: {e}", exc_info=True)
                response = f"Error sending email: {str(e)}"
        
        # Save and send response
        await db.add_chat_message(self.meeting_id, "assistant", response)
        await self.websocket.send_json({
            "type": "CHAT_RESPONSE",
            "meeting_id": self.meeting_id,
            "message": response
        })
    
    async def _handle_notion_command(self):
        """Handle Notion push command."""
        from app.services.notion_service import notion_service
        from app.config import settings
        
        try:
            # Check if Notion is configured
            if not settings.NOTION_API_KEY or not settings.NOTION_DATABASE_ID:
                response = "Notion integration is not configured. Please add NOTION_API_KEY and NOTION_DATABASE_ID to your .env file."
            else:
                # Get meeting data
                meeting_data = await db.get_meeting(self.meeting_id)
                if not meeting_data:
                    response = "Meeting not found."
                else:
                    # Get final summary
                    final_summary = await db.get_final_summary(self.meeting_id)
                    if not final_summary:
                        response = "No summary available yet. Please wait for the meeting to finish."
                    else:
                        # Push to Notion
                        page_url = await notion_service.push_summary(
                            meeting_id=self.meeting_id,
                            summary=final_summary,
                            title=meeting_data.get("title", "Meeting Summary")
                        )
                        
                        if page_url:
                            response = f"Summary pushed to Notion successfully!\n\n🔗 View here: {page_url}"
                            await db.log_integration(self.meeting_id, "notion", "success", {"url": page_url})
                        else:
                            response = "Failed to push to Notion. Please check your Notion configuration."
                            await db.log_integration(self.meeting_id, "notion", "failed")
        
        except Exception as e:
            logger.error(f"Notion command failed: {e}", exc_info=True)
            response = f" Error pushing to Notion: {str(e)}"
        
        # Save and send response
        await db.add_chat_message(self.meeting_id, "assistant", response)
        await self.websocket.send_json({
            "type": "CHAT_RESPONSE",
            "meeting_id": self.meeting_id,
            "message": response
        })
    
    async def _transcription_worker(self):
        """Background worker for periodic transcription.
        
        If ENABLE_STREAMING is true, uses Groq streaming API for real-time partial results.
        Otherwise, falls back to batch transcription every TRANSCRIPTION_WINDOW_SEC.
        """
        try:
            if settings.ENABLE_STREAMING:
                await self._streaming_transcription_worker()
            else:
                await self._batch_transcription_worker()
        except asyncio.CancelledError:
            logger.info("Transcription worker cancelled")
        except Exception as e:
            logger.error(f"Transcription worker error: {e}", exc_info=True)
    
    async def _batch_transcription_worker(self):
        """Original batch-based transcription worker."""
        try:
            while self.meeting_active:
                await asyncio.sleep(10)  # Check every 10 seconds
                
                # Get unprocessed audio
                result = self.audio_buffer.get_unprocessed_audio()
                
                # DEBUG: Log buffer state regardless of result
                total_audio_bytes = len(self.audio_buffer.buffer)
                processed_bytes = self.audio_buffer.processed_offset
                unprocessed_bytes = total_audio_bytes - processed_bytes
                unprocessed_secs = unprocessed_bytes / (settings.SAMPLE_RATE * 2)
                
                if result is None:
                    logger.debug(f"[WORKER] Buffer check: total={total_audio_bytes//(settings.SAMPLE_RATE*2)}s, processed={processed_bytes//(settings.SAMPLE_RATE*2)}s, unprocessed={unprocessed_secs:.1f}s < MIN_DURATION (no transcription)")
                    continue
                
                audio_np, bytes_processed = result
                duration_secs = bytes_processed / (settings.SAMPLE_RATE * 2)
                
                # Validate audio
                if not self.validator.validate_audio_array(audio_np):
                    logger.warning("Invalid audio array, skipping transcription")
                    continue
                
                # Transcribe
                text = await transcriber.transcribe(audio_np)
                
                # Always mark as processed, even if no text was returned
                # (empty result means silence, not an error)
                self.audio_buffer.mark_processed(bytes_processed)
                
                if text:
                    # Save to database
                    await db.add_transcript(self.meeting_id, text)
                    
                    # Send update
                    await self.websocket.send_json({
                        "type": "TRANSCRIPT_UPDATE",
                        "meeting_id": self.meeting_id,
                        "text": text,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
                    logger.info(f"[WORKER] Transcribed {duration_secs:.1f}s ({bytes_processed} bytes) -> {len(text)} chars")
                else:
                    logger.debug(f"[WORKER] No speech detected in {duration_secs:.1f}s ({bytes_processed} bytes)")
                    
        except asyncio.CancelledError:
            logger.info("Batch transcription worker cancelled")
        except Exception as e:
            logger.error(f"Batch transcription worker error: {e}", exc_info=True)
    
    async def _streaming_transcription_worker(self):
        """Streaming-based transcription worker using Groq API.
        
        Streams audio frames and broadcasts partial transcripts in real-time.
        Falls back to batch mode if streaming unavailable.
        """
        try:
            while self.meeting_active:
                await asyncio.sleep(5)  # Check every 5 seconds for new audio
                
                # Get unprocessed audio
                result = self.audio_buffer.get_unprocessed_audio()
                
                if result is None:
                    total_audio_bytes = len(self.audio_buffer.buffer)
                    processed_bytes = self.audio_buffer.processed_offset
                    unprocessed_secs = (total_audio_bytes - processed_bytes) / (settings.SAMPLE_RATE * 2)
                    logger.debug(f"[STREAMING] No audio ready (unprocessed={unprocessed_secs:.1f}s < MIN_DURATION)")
                    continue
                
                audio_np, bytes_processed = result
                duration_secs = bytes_processed / (settings.SAMPLE_RATE * 2)
                
                # Validate audio
                if not self.validator.validate_audio_array(audio_np):
                    logger.warning("[STREAMING] Invalid audio array, skipping transcription")
                    self.audio_buffer.mark_processed(bytes_processed)
                    continue
                
                logger.info(f"[STREAMING] Processing {duration_secs:.1f}s audio chunk with streaming API")
                
                # Use streaming transcriber
                accumulated_final_text = ""
                try:
                    async for result in streaming_transcriber.transcribe_streaming(audio_np):
                        if not self.meeting_active:
                            break
                        
                        # Send partial result to client
                        await self.websocket.send_json({
                            "type": "TRANSCRIPT_PARTIAL",
                            "meeting_id": self.meeting_id,
                            "text": result.text,
                            "is_final": result.is_final,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        
                        if result.is_final:
                            accumulated_final_text = result.text
                            logger.info(f"[STREAMING] Final result: {len(result.text)} chars")
                        else:
                            logger.debug(f"[STREAMING] Partial: {result.text[:50]}...")
                        
                        # Small delay to avoid overwhelming client
                        await asyncio.sleep(0.05)
                    
                    # Mark as processed after streaming completes
                    self.audio_buffer.mark_processed(bytes_processed)
                    
                    # Save final text to database
                    if accumulated_final_text:
                        await db.add_transcript(self.meeting_id, accumulated_final_text)
                        
                        # Send final update
                        await self.websocket.send_json({
                            "type": "TRANSCRIPT_UPDATE",
                            "meeting_id": self.meeting_id,
                            "text": accumulated_final_text,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                    
                except Exception as e:
                    logger.error(f"[STREAMING] Streaming transcription error: {e}", exc_info=True)
                    
                    # Fall back to batch transcription
                    logger.info("[STREAMING] Falling back to batch transcription")
                    try:
                        text = await transcriber.transcribe(audio_np)
                        self.audio_buffer.mark_processed(bytes_processed)
                        
                        if text:
                            await db.add_transcript(self.meeting_id, text)
                            await self.websocket.send_json({
                                "type": "TRANSCRIPT_UPDATE",
                                "meeting_id": self.meeting_id,
                                "text": text,
                                "timestamp": datetime.utcnow().isoformat()
                            })
                            logger.info(f"[STREAMING→BATCH] Transcribed {duration_secs:.1f}s -> {len(text)} chars")
                    except Exception as batch_error:
                        logger.error(f"[STREAMING→BATCH] Batch fallback also failed: {batch_error}", exc_info=True)
                        self.audio_buffer.mark_processed(bytes_processed)
                    
        except asyncio.CancelledError:
            logger.info("Streaming transcription worker cancelled")
        except Exception as e:
            logger.error(f"Streaming transcription worker error: {e}", exc_info=True)
    
    async def _summarization_worker(self):
        """Background worker for periodic summarization.
        
        When ENABLE_STREAMING is true, runs every 30 seconds (faster updates).
        Otherwise, runs every SUMMARY_INTERVAL_MIN (default 10 min).
        """
        try:
            # Determine interval based on mode
            if settings.ENABLE_STREAMING:
                interval = 30  # Real-time mode: update every 30 seconds
                logger.info("[SUMMARY] Running in STREAMING mode: 30-second intervals")
            else:
                interval = settings.summary_interval_seconds
                logger.info(f"[SUMMARY] Running in BATCH mode: {interval}-second intervals")
            
            while self.meeting_active:
                await asyncio.sleep(interval)
                
                # Get current transcript
                transcript = await db.get_full_transcript(self.meeting_id)
                
                if len(transcript) < 100:
                    logger.debug("[SUMMARY] Transcript too short, skipping summary")
                    continue
                
                # Generate intermediate summary
                summary = await summarizer.summarize_intermediate(transcript)
                
                # Save to database
                await db.add_summary(self.meeting_id, {"overview": summary}, is_final=False)
                
                # Send update
                await self.websocket.send_json({
                    "type": "SUMMARY_UPDATE",
                    "meeting_id": self.meeting_id,
                    "summary": summary,
                    "timestamp": datetime.utcnow().isoformat(),
                    "mode": "streaming" if settings.ENABLE_STREAMING else "batch"
                })
                
                logger.info(f"[SUMMARY] Generated periodic summary ({len(summary)} chars)")
                
        except asyncio.CancelledError:
            logger.info("Summarization worker cancelled")
        except Exception as e:
            logger.error(f"Summarization worker error: {e}", exc_info=True)
    
    async def _emergency_cleanup(self):
        """Emergency cleanup if connection drops without STOP."""
        logger.warning(f"Emergency cleanup for meeting {self.meeting_id}")
        self.meeting_active = False
        
        if self.transcription_task and not self.transcription_task.done():
            self.transcription_task.cancel()
        
        if self.summarization_task and not self.summarization_task.done():
            self.summarization_task.cancel()
        
        # Mark meeting as completed
        try:
            await db.update_meeting_status(self.meeting_id, "completed", datetime.utcnow())
        except:
            pass
    
    async def _send_error(self, error: str):
        """Send error message to client."""
        try:
            await self.websocket.send_json({
                "type": "ERROR",
                "error": error,
                "meeting_id": self.meeting_id
            })
        except:
            pass


async def meeting_websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint handler."""
    handler = MeetingWebSocketHandler(websocket)
    await handler.handle()