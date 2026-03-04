import React, { useState, useEffect, useCallback } from 'react';
import { Mic, Square, RotateCcw, MessageSquare, FileText } from 'lucide-react';
import { useAudioCapture } from '../hooks/useAudioCapture';
import { useWebSocket } from '../hooks/useWebSocket';
import { useAuth } from '../context/AuthContext';
import TranscriptPanel from '../components/TranscriptPanel';
import SummaryPanel from '../components/SummaryPanel';
import ChatPanel from '../components/ChatPanel';
import api from '../services/api';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

export default function MeetingPage() {
    const { user } = useAuth();
    const wsToken = localStorage.getItem('token');

    // -- State -------------------------------------------------------------
    const [transcripts, setTranscripts] = useState([]);
    const [interimTranscript, setInterimTranscript] = useState('');
    const [summary, setSummary] = useState('');
    const [status, setStatus] = useState(null); // { type, message }
    const [meetingId, setMeetingId] = useState(null);
    const [activeTab, setActiveTab] = useState('summary'); // 'summary' | 'chat'

    // Chat state
    const [chatMessages, setChatMessages] = useState([]);
    const [isChatLoading, setIsChatLoading] = useState(false);

    // -- Hooks -------------------------------------------------------------
    const { isRecording, startCapture, stopCapture, sampleRate } = useAudioCapture();

    const handleWebSocketMessage = useCallback((data) => {
        switch (data.type) {
            case 'connected':
                // Capture meeting ID from server
                if (data.meeting_id) {
                    setMeetingId(data.meeting_id);
                    console.log('Meeting ID:', data.meeting_id);
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
                setTranscripts(prev => [...prev, {
                    text: data.text,
                    speaker: data.speaker,
                    timestamp: new Date().toLocaleTimeString()
                }]);
                break;
            case 'interim':
                setInterimTranscript(data.text || '');
                break;
            case 'periodic_summary':
            case 'final_summary':
                setSummary(data.summary);
                setStatus({ type: 'success', message: 'Summary ready' });
                // Switch to summary tab if valid summary arrives and not checking chat
                if (activeTab !== 'chat') {
                    setActiveTab('summary');
                }
                break;
            case 'error':
                setStatus({ type: 'error', message: data.message });
                break;
            default:
                break;
        }
    }, [activeTab]);

    const { isConnected, sendMessage, connect, disconnect, disableReconnect } = useWebSocket(
        `${WS_URL}/meeting/ws${wsToken ? `?token=${encodeURIComponent(wsToken)}` : ''}`,
        handleWebSocketMessage
    );

    // -- Handlers ----------------------------------------------------------

    const handleStartRecording = async () => {
        disconnect();
        const newMeetingId = crypto.randomUUID().replace(/-/g, '');
        setMeetingId(newMeetingId);
        setTranscripts([]);
        setInterimTranscript('');
        setSummary('');
        setChatMessages([]);
        setStatus(null);

        const query = new URLSearchParams({ meeting_id: newMeetingId });
        if (wsToken) {
            query.set('token', wsToken);
        }
        connect(`${WS_URL}/meeting/ws?${query.toString()}`);
        sendMessage(JSON.stringify({
            type: 'config',
            sample_rate: sampleRate || 16000,
        }));

        // Start capture. Note: In a real app, we might wait for WS 'connected' event
        // with the meeting_id before starting audio, but here we can start capturing
        // and the WS will handle flow.
        const started = await startCapture((pcmFrame) => {
            // Drop stale audio if socket is down to avoid lag burst after reconnect.
            sendMessage(pcmFrame, { dropIfDisconnected: true });
        }, { output: 'arraybuffer' });

        if (!started) {
            setStatus({ type: 'error', message: 'Failed to access microphone' });
            disconnect();
        }
    };

    const handleStopRecording = () => {
        disableReconnect();
        stopCapture();
        sendMessage('STOP');
    };

    const handleEmail = async () => {
        setStatus({ type: 'loading', message: 'Sending email...' });
        sendMessage(`ACTION: EMAIL ${user.email}`);
    };

    const handleNotion = async () => {
        setStatus({ type: 'loading', message: 'Pushing to Notion...' });
        sendMessage('ACTION: NOTION');
    };

    const handleChatSubmit = async (text, voiceAudio = null) => {
        if (!meetingId) {
            setStatus({ type: 'error', message: 'No active meeting context' });
            return;
        }

        // Add user message immediately
        const userMsg = { role: 'user', content: text || '(Voice Message)' };
        setChatMessages(prev => [...prev, userMsg]);
        setIsChatLoading(true);

        try {
            const response = await api.post(`/meeting/${meetingId}/chat`, {
                query: text,
                voice_audio: voiceAudio
            });

            // Add AI response
            const aiMsg = { role: 'assistant', content: response.data.response };
            setChatMessages(prev => [...prev, aiMsg]);
        } catch (error) {
            console.error('Chat error:', error);
            setChatMessages(prev => [...prev, {
                role: 'assistant',
                content: 'Sorry, I encountered an error answering your question.'
            }]);
        } finally {
            setIsChatLoading(false);
        }
    };

    // Cleanup
    useEffect(() => {
        return () => {
            stopCapture();
            disconnect();
        };
    }, []);

    // -- Render ------------------------------------------------------------
    return (
        <div className="h-[calc(100vh-64px)] flex flex-col p-4 gap-4 max-w-7xl mx-auto">

            {/* Top Bar Controls */}
            <div className="flex items-center justify-between bg-white border border-slate-200 p-4 rounded-2xl shadow-sm">
                <div className="flex items-center gap-4">
                    {!isRecording ? (
                        <button
                            onClick={handleStartRecording}
                            className="flex items-center gap-2 px-6 py-3 bg-slate-900 hover:bg-slate-700 text-white rounded-xl font-semibold transition-all shadow-md"
                        >
                            <Mic size={20} />
                            Start Meeting
                        </button>
                    ) : (
                        <button
                            onClick={handleStopRecording}
                            className="flex items-center gap-2 px-6 py-3 bg-rose-500 hover:bg-rose-600 text-white rounded-xl font-semibold transition-all shadow-md"
                        >
                            <Square size={20} />
                            Stop Recording
                        </button>
                    )}

                    <div className="flex items-center gap-2 text-slate-500 text-sm ml-4">
                        <div className={`w-2.5 h-2.5 rounded-full ${isConnected ? 'bg-green-500' : 'bg-slate-600'}`} />
                        {isConnected ? 'Connected' : 'Disconnected'}
                        {meetingId && <span className="text-xs opacity-50 ml-2">ID: {meetingId.slice(0, 8)}</span>}
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    <button
                        onClick={() => {
                            setTranscripts([]);
                            setInterimTranscript('');
                            setChatMessages([]);
                            setSummary('');
                        }}
                        className="p-2 hover:bg-slate-100 rounded-lg text-slate-500 transition-colors"
                        title="Reset Meeting Context"
                    >
                        <RotateCcw size={20} />
                    </button>
                </div>
            </div>

            {/* Main Content Info */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 flex-1 min-h-0">

                {/* Left Column: Transcript */}
                <div className="flex flex-col h-full min-h-0">
                    <h2 className="text-lg font-semibold text-slate-800 mb-2 px-1">Live Transcript</h2>
                    <TranscriptPanel
                        transcripts={transcripts}
                        interimTranscript={interimTranscript}
                        isRecording={isRecording}
                    />
                </div>

                {/* Right Column: Information & Chat */}
                <div className="flex flex-col h-full min-h-0 bg-white rounded-2xl border border-slate-200 overflow-hidden">

                    {/* Tabs Header */}
                    <div className="flex border-b border-slate-200 bg-white">
                        <button
                            onClick={() => setActiveTab('summary')}
                            className={`flex items-center gap-2 px-6 py-3 text-sm font-medium transition-colors relative
                                ${activeTab === 'summary' ? 'text-slate-900' : 'text-slate-500 hover:text-slate-700'}
                            `}
                        >
                            <FileText size={16} />
                            Summary & Actions
                            {activeTab === 'summary' && (
                                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-amber-500" />
                            )}
                        </button>
                        <button
                            onClick={() => setActiveTab('chat')}
                            className={`flex items-center gap-2 px-6 py-3 text-sm font-medium transition-colors relative
                                ${activeTab === 'chat' ? 'text-slate-900' : 'text-slate-500 hover:text-slate-700'}
                            `}
                        >
                            <MessageSquare size={16} />
                            Chat with Transcript (try: "push this to notion", "send this to a@x.com")
                            {activeTab === 'chat' && (
                                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-amber-500" />
                            )}
                        </button>
                    </div>

                    {/* Tab Content */}
                    <div className="flex-1 min-h-0 relative">
                        {activeTab === 'summary' ? (
                            <div className="absolute inset-0 p-4 overflow-y-auto">
                                <SummaryPanel
                                    summary={summary}
                                    onEmail={handleEmail}
                                    onNotion={handleNotion}
                                    status={status}
                                    isLoading={status?.type === 'loading'}
                                />
                            </div>
                        ) : (
                            <div className="absolute inset-0">
                                <ChatPanel
                                    messages={chatMessages}
                                    onSendMessage={handleChatSubmit}
                                    isLoading={isChatLoading}
                                    placeholder="Ask questions about the meeting..."
                                />
                            </div>
                        )}
                    </div>
                </div>

            </div>

        </div>
    );
}
