import { Trash2, Upload, Sparkles, CircleHelp, Database } from 'lucide-react';
import ChatPanel from '../components/ChatPanel';
import { useChat } from '../context/ChatContext';
import api from '../services/api';
import { useEffect, useState } from 'react';
import useInterval from '../hooks/useInterval';

export default function ChatPage() {
    const {
        messages,
        isLoading,
        isUploading,
        uploadStatus,
        llmStatus,
        sendMessage,
        clearMessages,
        uploadDoc,
        clearDocs,
        setUploadStatus,
    } = useChat();
    const [recentJobs, setRecentJobs] = useState([]);
    const [jobStatuses, setJobStatuses] = useState({});

    useEffect(() => {
        try {
            const stored = localStorage.getItem('doc_jobs');
            setRecentJobs(stored ? JSON.parse(stored) : []);
        } catch {
            setRecentJobs([]);
        }
    }, [uploadStatus]);

    // Poll job status for recent uploads
    useInterval(async () => {
        if (!recentJobs.length) return;
        const updated = {};
        for (const job of recentJobs.slice(0, 3)) {
            try {
                const res = await api.get(`/docs/status/${job.jobId}`);
                updated[job.jobId] = res.data.status;
            } catch {
                // ignore
            }
        }
        if (Object.keys(updated).length) {
            setJobStatuses((prev) => ({ ...prev, ...updated }));
        }
    }, 4000);

    const handleSendMessage = async (text, voiceAudio = null) => {
        await sendMessage(text, voiceAudio);
    };

    const handleFileUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        await uploadDoc(file);
        e.target.value = '';
    };

    const handleClearDocs = async () => {
        if (!confirm('Clear all uploaded documents?')) return;
        try {
            await clearDocs();
        } catch (_error) {
            setUploadStatus({ type: 'error', message: 'Failed to clear documents' });
        }
    };

    const handleClearHistory = async () => {
        if (!confirm('Clear chat history?')) return;
        try {
            await api.delete('/chat/history');
        } catch (error) {
            console.error('Clear history error:', error);
        }
        clearMessages();
    };

    return (
        <div className="h-[calc(100vh-64px)] p-4 md:p-6 max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-5">
            <aside className="space-y-4">
                <div className="rounded-2xl border border-amber-200 bg-gradient-to-br from-amber-50 via-white to-orange-50 p-5 shadow-sm">
                    <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
                        <Sparkles size={18} className="text-amber-600" />
                        Chat + Knowledge
                    </h1>
                    <p className="text-sm text-slate-600 mt-2">
                        Upload your files or directly chat with the agent.
                    </p>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                    <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                        <CircleHelp size={16} className="text-amber-600" />
                        What you can do here
                    </h2>
                    <ul className="mt-3 text-sm text-slate-600 space-y-2">
                        <li className="flex items-start gap-2"><Database size={14} className="mt-1 text-amber-500" />Upload docs and ask grounded questions.</li>
                        <li className="flex items-start gap-2"><Sparkles size={14} className="mt-1 text-amber-500" />Chat normally with or without documents.</li>
                    </ul>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                    <label className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-900 text-white text-sm cursor-pointer hover:bg-slate-700 transition-colors">
                        <Upload size={16} />
                        {isUploading ? 'Uploading...' : 'Upload PDF/TXT'}
                        <input
                            type="file"
                            accept=".pdf,.txt"
                            className="hidden"
                            disabled={isUploading}
                            onChange={handleFileUpload}
                        />
                    </label>
                    {uploadStatus && (
                        <p className={`text-xs mt-3 ${uploadStatus.type === 'error' ? 'text-rose-600' : 'text-emerald-600'}`}>
                            {uploadStatus.message}
                        </p>
                    )}
                    {recentJobs.length > 0 && (
                        <div className="mt-3 text-xs text-slate-600">
                            <div className="font-semibold text-slate-800 mb-1">Recent ingestion jobs</div>
                            <ul className="space-y-1">
                                {recentJobs.slice(0,3).map((j) => (
                                    <li key={j.jobId} className="flex items-center justify-between">
                                        <span className="truncate max-w-[140px]">{j.filename}</span>
                                        <span className="text-[11px] text-slate-500">
                                            {jobStatuses[j.jobId] ? jobStatuses[j.jobId] : `${j.jobId.slice(0,8)}...`}
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                    <div className="flex items-center gap-2 mt-4">
                        <button
                            onClick={handleClearDocs}
                            className="text-sm px-3 py-2 rounded-lg border border-slate-300 hover:bg-slate-100 text-slate-700"
                        >
                            Clear Docs
                        </button>
                        <button
                            onClick={handleClearHistory}
                            className="text-sm px-3 py-2 rounded-lg border border-slate-300 hover:bg-rose-50 hover:border-rose-200 hover:text-rose-700 text-slate-700 flex items-center gap-2"
                        >
                            <Trash2 size={14} />
                            Clear Chat
                        </button>
                    </div>
                    {llmStatus && (
                        <div className={`mt-3 text-xs px-3 py-2 rounded-lg ${llmStatus.type === 'warning' ? 'bg-amber-50 text-amber-700 border border-amber-200' : 'bg-rose-50 text-rose-700 border border-rose-200'}`}>
                            {llmStatus.message}
                        </div>
                    )}
                </div>
            </aside>

            <div className="lg:col-span-2 min-h-0">
                <div className="h-full min-h-[520px]">
                    <ChatPanel
                        messages={messages}
                        onSendMessage={handleSendMessage}
                        isLoading={isLoading}
                        placeholder="Ask anything..."
                        enableVoiceInput={false}
                        enableVoiceReply={false}
                    />
                </div>
            </div>
        </div>
    );
}
