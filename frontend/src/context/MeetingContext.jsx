import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useAudioCapture } from '../hooks/useAudioCapture';
import { useWebSocket } from '../hooks/useWebSocket';
import api from '../services/api';
import { useAuth } from './AuthContext';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

const MeetingContext = createContext(null);

export function MeetingProvider({ children }) {
  const { user } = useAuth();
  const wsToken = localStorage.getItem('token');

  const [meetingId, setMeetingId] = useState(null);
  const [transcripts, setTranscripts] = useState([]);
  const [interimTranscript, setInterimTranscript] = useState('');
  const [summary, setSummary] = useState('');
  const [status, setStatus] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const [isChatLoading, setIsChatLoading] = useState(false);

  const { isRecording, startCapture, stopCapture, sampleRate } = useAudioCapture();

  const handleWebSocketMessage = useCallback((data) => {
    switch (data.type) {
      case 'connected':
        if (data.meeting_id) {
          setMeetingId(data.meeting_id);
        }
        setStatus({ type: 'success', message: 'Connected' });
        break;
      case 'status':
        setStatus({
          type: data.message?.toLowerCase().includes('generating') ? 'loading' : 'success',
          message: data.message || 'Status update',
        });
        break;
      case 'transcript':
        setInterimTranscript('');
        setTranscripts((prev) => [
          ...prev,
          {
            text: data.text,
            speaker: data.speaker,
            timestamp: new Date().toLocaleTimeString(),
          },
        ]);
        break;
      case 'interim':
        setInterimTranscript(data.text || '');
        break;
      case 'periodic_summary':
      case 'final_summary':
        setSummary(data.summary);
        setStatus({ type: 'success', message: 'Summary ready' });
        break;
      case 'error':
        setStatus({ type: 'error', message: data.message });
        break;
      default:
        break;
    }
  }, []);

  const { isConnected, sendMessage, connect, disconnect, disableReconnect } = useWebSocket(
    `${WS_URL}/meeting/ws${wsToken ? `?token=${encodeURIComponent(wsToken)}` : ''}`,
    handleWebSocketMessage
  );

  const startMeeting = useCallback(async () => {
    // if already recording, no-op
    if (isRecording) return;

    setTranscripts([]);
    setInterimTranscript('');
    setSummary('');
    setChatMessages([]);
    setStatus(null);

    // create or reuse meeting id
    const newMeetingId = crypto.randomUUID().replace(/-/g, '');
    setMeetingId(newMeetingId);

    const query = new URLSearchParams({ meeting_id: newMeetingId });
    if (wsToken) query.set('token', wsToken);
    connect(`${WS_URL}/meeting/ws?${query.toString()}`);

    // Send sample rate config after connect attempt
    sendMessage(
      JSON.stringify({
        type: 'config',
        sample_rate: sampleRate || 16000,
      })
    );

    const started = await startCapture(
      (pcmFrame) => {
        sendMessage(pcmFrame, { dropIfDisconnected: true });
      },
      { output: 'arraybuffer' }
    );

    if (!started) {
      setStatus({ type: 'error', message: 'Failed to access microphone' });
      disconnect();
    }
  }, [connect, sendMessage, startCapture, sampleRate, wsToken, isRecording, disconnect]);

  const stopMeeting = useCallback(() => {
    disableReconnect();
    stopCapture();
    sendMessage('STOP');
    disconnect();
  }, [disableReconnect, stopCapture, sendMessage, disconnect]);

  const sendEmail = useCallback(() => {
    if (!meetingId) return;
    setStatus({ type: 'loading', message: 'Sending email...' });
    sendMessage(`ACTION: EMAIL ${user?.email || ''}`);
  }, [meetingId, sendMessage, user]);

  const sendNotion = useCallback(() => {
    if (!meetingId) return;
    setStatus({ type: 'loading', message: 'Pushing to Notion...' });
    sendMessage('ACTION: NOTION');
  }, [meetingId, sendMessage]);

  const sendMeetingChat = useCallback(
    async (text, voiceAudio = null) => {
      if (!meetingId) {
        setStatus({ type: 'error', message: 'No active meeting context' });
        return;
      }

      const userMsg = { role: 'user', content: text || '(Voice Message)' };
      setChatMessages((prev) => [...prev, userMsg]);
      setIsChatLoading(true);

      try {
        const response = await api.post(`/meeting/${meetingId}/chat`, {
          query: text,
          voice_audio: voiceAudio,
        });
        const aiMsg = { role: 'assistant', content: response.data.response };
        setChatMessages((prev) => [...prev, aiMsg]);
      } catch (error) {
        console.error('Chat error:', error);
        setChatMessages((prev) => [
          ...prev,
          { role: 'assistant', content: 'Sorry, I encountered an error answering your question.' },
        ]);
      } finally {
        setIsChatLoading(false);
      }
    },
    [meetingId]
  );

  // On app unmount only
  useEffect(() => {
    return () => {
      stopCapture();
      disconnect();
    };
  }, [stopCapture, disconnect]);

  useEffect(() => {
    const handler = () => {
      stopMeeting();
      stopCapture();
      disconnect();
    };
    window.addEventListener('app:logout', handler);
    return () => window.removeEventListener('app:logout', handler);
  }, [stopMeeting, stopCapture, disconnect]);

  return (
    <MeetingContext.Provider
      value={{
        meetingId,
        transcripts,
        interimTranscript,
        summary,
        status,
        setStatus,
        chatMessages,
        isChatLoading,
        isRecording,
        isConnected,
        startMeeting,
        stopMeeting,
        sendMeetingChat,
        sendEmail,
        sendNotion,
        setChatMessages,
        setTranscripts,
        setInterimTranscript,
        setSummary,
      }}
    >
      {children}
    </MeetingContext.Provider>
  );
}

export function useMeeting() {
  const ctx = useContext(MeetingContext);
  if (!ctx) throw new Error('useMeeting must be used within MeetingProvider');
  return ctx;
}
