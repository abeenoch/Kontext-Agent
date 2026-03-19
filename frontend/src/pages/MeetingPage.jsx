import React, { useState } from 'react';
import { Mic, Square, RotateCcw, MessageSquare, FileText } from 'lucide-react';
import { useMeeting } from '../context/MeetingContext';
import TranscriptPanel from '../components/TranscriptPanel';
import SummaryPanel from '../components/SummaryPanel';
import ChatPanel from '../components/ChatPanel';

export default function MeetingPage() {
    const [activeTab, setActiveTab] = useState('summary');

    const {
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
    } = useMeeting();

    // -- Handlers ----------------------------------------------------------

    const handleStartRecording = async () => {
        await startMeeting();
    };

    const handleStopRecording = () => {
        stopMeeting();
    };

    const handleEmail = async () => {
        setStatus({ type: 'loading', message: 'Sending email...' });
        sendEmail();
    };

    const handleNotion = async () => {
        setStatus({ type: 'loading', message: 'Pushing to Notion...' });
        sendNotion();
    };

    const handleChatSubmit = async (text, voiceAudio = null) => {
        await sendMeetingChat(text, voiceAudio);
    };

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
