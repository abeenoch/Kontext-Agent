import { Upload, FileText, X, Trash2 } from 'lucide-react';
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
        clearChat,
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

        const activeJobs = recentJobs.filter(
            (j) => !['completed', 'failed'].includes(jobStatuses[j.jobId])
        );
        if (!activeJobs.length) return;

        const updated = {};
        for (const job of activeJobs.slice(0, 5)) {
            try {
                const params = job.tabId ? { tab_id: job.tabId } : undefined;
                const res = await api.get(`/docs/status/${job.jobId}`, { params });
                updated[job.jobId] = res.data.status;
            } catch {
                // ignore polling errors
            }
        }

        if (Object.keys(updated).length) {
            const mergedStatuses = { ...jobStatuses, ...updated };
            setJobStatuses(mergedStatuses);

            // Drop completed/failed jobs from the sidebar and localStorage
            const remaining = recentJobs.filter(
                (j) => !['completed', 'failed'].includes(mergedStatuses[j.jobId])
            );
            setRecentJobs(remaining);
            try {
                localStorage.setItem('doc_jobs', JSON.stringify(remaining));
            } catch {
                /* ignore */
            }
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
            setRecentJobs([]);
            setJobStatuses({});
            localStorage.removeItem('doc_jobs');
        } catch (_error) {
            setUploadStatus({ type: 'error', message: 'Failed to clear documents' });
        }
    };

    const handleClearChat = async () => {
        if (!confirm('Clear chat history? This removes messages but keeps uploads.')) return;
        await clearChat();
    };

    return (
        <div className="h-[calc(100vh-64px)] p-3 md:p-6 max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-[280px_1fr] gap-4">
            {/* Sidebar */}
            <aside className="bg-white border border-slate-200 rounded-2xl shadow-sm flex flex-col">
                <div className="p-4 border-b border-slate-200">
                    <div className="text-sm font-semibold text-slate-900">Knowledge Base</div>
                    <p className="text-xs text-slate-500 mt-1">
                        Uploads here power the single shared chat space.
                    </p>
                </div>

                <div className="p-4 space-y-3 flex-1 overflow-y-auto">
                    <label className="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-900 text-white text-sm cursor-pointer hover:bg-slate-700 transition-colors">
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
                        <p className={`text-xs ${uploadStatus.type === 'error' ? 'text-rose-600' : 'text-emerald-600'}`}>
                            {uploadStatus.message}
                        </p>
                    )}
                    {recentJobs.length > 0 && (
                        <div className="text-xs text-slate-600 space-y-1">
                            <div className="font-semibold text-slate-800">Ingestion jobs</div>
                            <ul className="space-y-1">
                                {recentJobs
                                    .slice(0, 5)
                                    .map((j) => (
                                        <li key={j.jobId} className="flex items-center justify-between">
                                            <span className="truncate max-w-[140px] flex items-center gap-1">
                                                <FileText size={12} />
                                                {j.filename}
                                            </span>
                                            <span className="text-[11px] text-slate-500">
                                                {jobStatuses[j.jobId] ? jobStatuses[j.jobId] : `${j.jobId.slice(0, 8)}...`}
                                            </span>
                                        </li>
                                    ))}
                            </ul>
                        </div>
                    )}
                    <button
                        onClick={handleClearDocs}
                        className="w-full text-sm px-3 py-2 rounded-lg border border-slate-300 hover:bg-slate-100 text-slate-700"
                    >
                        Clear Knowledge Base
                    </button>
                    {llmStatus && (
                        <div
                            className={`text-xs px-3 py-2 rounded-lg ${
                                llmStatus.type === 'warning'
                                    ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                    : 'bg-rose-50 text-rose-700 border border-rose-200'
                            }`}
                        >
                            {llmStatus.message}
                        </div>
                    )}
                </div>
            </aside>

            {/* Main chat area */}
            <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-3 md:p-4 flex flex-col">
                <div className="flex items-center justify-between mb-3">
                    <div className="flex flex-col gap-0.5">
                        <div className="text-sm font-semibold text-slate-900">Chat</div>
                        <div className="text-xs text-slate-500">
                            All messages share one knowledge base; upload once and chat freely.
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={handleClearChat}
                            className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-100 text-slate-700"
                            title="Clear chat history"
                        >
                            <Trash2 size={14} />
                            Clear chat
                        </button>
                        {uploadStatus && uploadStatus.type === 'error' && (
                            <div className="flex items-center gap-2 text-xs text-rose-700 bg-rose-50 border border-rose-200 px-3 py-1.5 rounded-lg">
                                <X size={14} />
                                {uploadStatus.message}
                            </div>
                        )}
                    </div>
                </div>
                <div className="flex-1 min-h-[520px]">
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
