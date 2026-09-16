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
        sendSlack,
        setChatMessages,
        setTranscripts,
        setInterimTranscript,
        setSummary,
    } = useMeeting();

    // -- Handlers ----------------------------------------------------------

    const handleStartRecording = async () => {
        console.log('[MeetingPage] handleStartRecording called');
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

    const handleSlack = async () => {
        setStatus({ type: 'loading', message: 'Posting to Slack...' });
        sendSlack();
    };

    const handleChatSubmit = async (text, voiceAudio = null) => {
        await sendMeetingChat(text, voiceAudio);
    };

    // -- Render ------------------------------------------------------------
    return (
        <div className="h-[calc(100vh-64px)] flex flex-col p-3 md:p-4 gap-4 w-full max-w-7xl mx-auto">

            {/* Top Bar Controls */}
            <div className="flex flex-wrap items-center justify-between bg-white border border-slate-200 p-3 md:p-4 rounded-2xl shadow-sm gap-3">
                <div className="flex items-center gap-3 md:gap-4">
                    {!isRecording ? (
                        <button
                            onClick={handleStartRecording}
                            className="flex items-center gap-2 px-4 md:px-6 py-2.5 md:py-3 bg-slate-900 hover:bg-slate-700 text-white rounded-xl font-semibold transition-all shadow-md text-sm md:text-base"
                        >
                            <Mic size={18} />
                            Start Meeting
                        </button>
                    ) : (
                        <button
                            onClick={handleStopRecording}
                            className="flex items-center gap-2 px-4 md:px-6 py-2.5 md:py-3 bg-rose-500 hover:bg-rose-600 text-white rounded-xl font-semibold transition-all shadow-md text-sm md:text-base"
                        >
                            <Square size={18} />
                            Stop Recording
                        </button>
                    )}

                    <div className="flex items-center gap-2 text-slate-500 text-xs md:text-sm">
                        <div className={`w-2.5 h-2.5 rounded-full ${isConnected ? 'bg-green-500' : 'bg-slate-600'}`} />
                        <span className="hidden sm:inline">{isConnected ? 'Connected' : 'Disconnected'}</span>
                        {meetingId && <span className="text-xs opacity-50 ml-1 hidden sm:inline">ID: {meetingId.slice(0, 8)}</span>}
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
                        className="p-2.5 hover:bg-slate-100 rounded-lg text-slate-500 transition-colors"
                        title="Reset Meeting Context"
                    >
                        <RotateCcw size={18} />
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
                            className={`flex items-center gap-2 px-4 md:px-6 py-3 text-sm font-medium transition-colors relative whitespace-nowrap
                                ${activeTab === 'summary' ? 'text-slate-900' : 'text-slate-500 hover:text-slate-700'}
                            `}
                        >
                            <FileText size={16} />
                            <span className="hidden sm:inline">Summary &amp; Actions</span>
                            <span className="sm:hidden">Summary</span>
                            {activeTab === 'summary' && (
                                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-amber-500" />
                            )}
                        </button>
                        <button
                            onClick={() => setActiveTab('chat')}
                            className={`flex items-center gap-2 px-4 md:px-6 py-3 text-sm font-medium transition-colors relative whitespace-nowrap
                                ${activeTab === 'chat' ? 'text-slate-900' : 'text-slate-500 hover:text-slate-700'}
                            `}
                        >
                            <MessageSquare size={16} />
                            <span className="hidden sm:inline">Chat with Transcript</span>
                            <span className="sm:hidden">Chat</span>
                            {activeTab === 'chat' && (
                                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-amber-500" />
                            )}
                        </button>
                    </div>

                    {/* Tab Content */}
                    <div className="flex-1 min-h-0 relative">
                        {activeTab === 'summary' ? (
                            <div className="absolute inset-0 p-3 md:p-4 overflow-y-auto">
                                <SummaryPanel
                                    summary={summary}
                                    onEmail={handleEmail}
                                    onNotion={handleNotion}
                                    onSlack={handleSlack}
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
