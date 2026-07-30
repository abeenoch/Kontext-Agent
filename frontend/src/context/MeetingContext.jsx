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
  const [awaitingFinal, setAwaitingFinal] = useState(false);

  const { isRecording, startCapture, stopCapture, sampleRate } = useAudioCapture();

  const handleWebSocketMessage = useCallback((data) => {
    switch (data.type) {
      case 'connected':
        if (data.meeting_id) {
          setMeetingId(data.meeting_id);
        }
        setStatus({ type: 'success', message: 'Connected' });
        setAwaitingFinal(false);
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
        setSummary(data.summary);
        setStatus({ type: 'success', message: 'Periodic summary ready' });
        setAwaitingFinal(false);
        break;
      case 'final_summary':
        setSummary(data.summary);
        setStatus({ type: 'success', message: 'Final summary ready' });
        setAwaitingFinal(false);
        // Graceful close after final summary to avoid missing message
        setTimeout(() => disconnect(), 300);
        break;
      case 'error':
        setStatus({ type: 'error', message: data.message });
        setAwaitingFinal(false);
        break;
      default:
        break;
    }
  }, []);

  const { isConnected, sendMessage, connect, disconnect, disableReconnect } = useWebSocket(
    `${WS_URL}/meeting/ws${wsToken ? `?token=${encodeURIComponent(wsToken)}` : ''}`,
    handleWebSocketMessage,
    {
      onOpen: () => {
        // Ensure server knows sample rate after any (re)connect.
        sendMessage(
          JSON.stringify({
            type: 'config',
            sample_rate: sampleRate || 16000,
          })
        );
      },
    }
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
    const newMeetingId = (
      typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
            (c ^ (Math.random() * 16 >> c / 4)).toString(16))
    ).replace(/-/g, '');
    setMeetingId(newMeetingId);

    const query = new URLSearchParams({ meeting_id: newMeetingId });
    if (wsToken) query.set('token', wsToken);
    console.log('[MeetingContext] Starting connection to:', `${WS_URL}/meeting/ws?${query.toString()}`);
    connect(`${WS_URL}/meeting/ws?${query.toString()}`);

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
    stopCapture(); // stop mic immediately
    disableReconnect(); // don't reconnect, but keep socket open for final summary
    setAwaitingFinal(true);
    setStatus({ type: 'loading', message: 'Generating final summary...' });
    sendMessage('STOP');
  }, [disableReconnect, stopCapture, sendMessage]);

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

  const sendSlack = useCallback((channel = null) => {
    if (!meetingId) return;
    setStatus({ type: 'loading', message: 'Posting to Slack...' });
    const cmd = channel ? `ACTION: SLACK ${channel}` : 'ACTION: SLACK';
    sendMessage(cmd);
  }, [meetingId, sendMessage]);

  const sendMeetingChat = useCallback(
    async (text, voiceAudio = null) => {
      const targetMeetingId = meetingId || 'recent';
      const isCrossMeeting = ['any', 'recent', 'latest'].includes(targetMeetingId) || !meetingId;

      // Detect temporal references so we route to cross-meeting search even on a specific meeting
      const temporalPattern = /\b(yesterday|last\s+\w+|this\s+week|last\s+week|two\s+days|three\s+days|\d+\s+days?\s+ago|monday|tuesday|wednesday|thursday|friday|saturday|sunday|earlier\s+today|this\s+morning|this\s+afternoon)\b/i;
      const hasTemporalRef = temporalPattern.test(text || '');
      const useCrossMeeting = isCrossMeeting || hasTemporalRef;

      const userMsg = { role: 'user', content: text || '(Voice Message)' };
      setChatMessages((prev) => [...prev, userMsg]);
      setIsChatLoading(true);

      try {
        let content, sources;

        if (useCrossMeeting) {
          const response = await api.post('/meeting/search', {
            query: text,
            date_hint: null,
          });
          content = response.data.answer;
          sources = response.data.sources?.length ? response.data.sources : null;
        } else {
          const response = await api.post(`/meeting/${targetMeetingId}/chat`, {
            query: text,
            voice_audio: voiceAudio,
          });
          content = response.data.response;
          // Capture sources if the backend returns them (e.g. from cross-meeting delegation)
          sources = response.data.sources?.length ? response.data.sources : null;
        }

        const aiMsg = { role: 'assistant', content, sources };
        setChatMessages((prev) => [...prev, aiMsg]);
      } catch (error) {
        console.error('Chat error:', error);
        const detail =
          error.response?.data?.detail ||
          (error.response?.status === 503
            ? 'LLM temporarily unavailable. Please retry.'
            : 'Sorry, I encountered an error answering your question.');
        setChatMessages((prev) => [...prev, { role: 'assistant', content: detail }]);
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
        sendSlack,
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
