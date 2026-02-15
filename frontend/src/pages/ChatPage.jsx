import { useState } from 'react';
import ChatPanel from '../components/ChatPanel';
import api from '../services/api';
import { Trash2, Upload, Sparkles, CircleHelp, Database } from 'lucide-react';

export default function ChatPage() {
    const [messages, setMessages] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadStatus, setUploadStatus] = useState(null);

    const handleSendMessage = async (text, voiceAudio = null) => {
        setIsLoading(true);

        const userMsg = { role: 'user', content: text || 'Message' };
        setMessages(prev => [...prev, userMsg]);

        try {
            const payload = {
                query: text,
                voice_audio: voiceAudio
            };

            const response = await api.post('/chat/query', payload);
            const { response: aiText } = response.data;

            setMessages(prev => [...prev, {
                role: 'assistant',
                content: aiText
            }]);
        } catch (error) {
            console.error('Chat error:', error);
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: 'Error processing request.',
                error: true
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleFileUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setIsUploading(true);
        setUploadStatus(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            await api.post('/docs/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            setUploadStatus({ type: 'success', message: `Uploaded ${file.name}` });
        } catch (error) {
            setUploadStatus({
                type: 'error',
                message: error.response?.data?.detail || 'Upload failed'
            });
        } finally {
            setIsUploading(false);
            e.target.value = '';
        }
    };

    const handleClearDocs = async () => {
        if (!confirm('Clear all uploaded documents?')) return;
        try {
            await api.delete('/docs/clear');
            setUploadStatus({ type: 'success', message: 'Knowledge base cleared' });
        } catch (_error) {
            setUploadStatus({ type: 'error', message: 'Failed to clear documents' });
        }
    };

    const handleClearHistory = async () => {
        if (!confirm('Clear chat history?')) return;
        try {
            await api.delete('/chat/history');
            setMessages([]);
        } catch (error) {
            console.error('Clear history error:', error);
        }
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
