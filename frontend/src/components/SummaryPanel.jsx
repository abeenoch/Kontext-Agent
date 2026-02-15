import { Mail, FileText, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

export default function SummaryPanel({ summary, onEmail, onNotion, status, isLoading }) {
    if (!summary && !isLoading) {
        return (
            <div className="bg-white border border-slate-200 rounded-2xl p-8 flex flex-col text-slate-500 h-full border-dashed">
                <div className="flex-1 flex flex-col items-center justify-center">
                    <FileText size={48} className="mb-4 opacity-20" />
                    <p className="text-sm font-medium">Summary will generate automatically</p>
                    <p className="text-xs mt-2 text-slate-500">Detailed notes appear here after sufficient context is gathered.</p>
                </div>

                {status && (
                    <div className={`
                        mt-4 px-4 py-3 text-sm border border-slate-200 rounded-lg flex items-center gap-2
                        ${status.type === 'error' ? 'text-red-700 bg-red-50' :
                            status.type === 'success' ? 'text-emerald-700 bg-emerald-50' :
                                'text-amber-700 bg-amber-50'}
                    `}>
                        {status.type === 'error' ? <AlertCircle size={16} /> :
                            status.type === 'success' ? <CheckCircle size={16} /> :
                                <Loader2 size={16} className="animate-spin" />}
                        <span className="font-medium">{status.message}</span>
                    </div>
                )}
            </div>
        );
    }

    return (
        <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden flex flex-col h-full shadow-sm relative">
            {isLoading && (
                <div className="absolute inset-0 bg-white/90 backdrop-blur-sm z-20 flex items-center justify-center flex-col gap-3">
                    <Loader2 className="animate-spin text-amber-600" size={32} />
                    <p className="text-slate-500 text-sm animate-pulse">Generating summary...</p>
                </div>
            )}

            <div className="p-4 border-b border-slate-200 bg-white flex items-center justify-between sticky top-0 z-10">
                <h3 className="font-semibold text-slate-900 flex items-center gap-2">
                    <FileText size={18} className="text-amber-600" />
                    Meeting Summary
                </h3>
                <div className="flex gap-2">
                    <button
                        onClick={onNotion}
                        disabled={isLoading || !summary}
                        title="Push to Notion"
                        className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed border border-slate-200"
                    >
                        <img src="https://upload.wikimedia.org/wikipedia/commons/4/45/Notion_app_logo.png" alt="Notion" className="w-4 h-4 opacity-80" />
                    </button>
                    <button
                        onClick={onEmail}
                        disabled={isLoading || !summary}
                        title="Email Summary"
                        className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed border border-slate-200"
                    >
                        <Mail size={16} />
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-6 text-slate-700 prose prose-sm max-w-none custom-scrollbar">
                <ReactMarkdown>{summary}</ReactMarkdown>
            </div>

            {status && (
                <div className={`
          px-4 py-3 text-sm border-t border-slate-200 flex items-center gap-2 
          ${status.type === 'error' ? 'text-red-700 bg-red-50' :
                        status.type === 'success' ? 'text-emerald-700 bg-emerald-50' :
                            'text-amber-700 bg-amber-50'}
        `}>
                    {status.type === 'error' ? <AlertCircle size={16} /> :
                        status.type === 'success' ? <CheckCircle size={16} /> :
                            <Loader2 size={16} className="animate-spin" />}
                    <span className="font-medium">{status.message}</span>
                </div>
            )}
        </div>
    );
}
