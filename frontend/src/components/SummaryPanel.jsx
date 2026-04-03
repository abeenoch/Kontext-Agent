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
                        <svg className="w-4 h-4 opacity-80" viewBox="0 0 100 100" fill="currentColor" xmlns="http://www.w3.org/2000/svg"><path d="M6 4.8C9.3 7.4 10.6 7.2 17 6.8l57.4-3.4c1.3 0 .2-1.3-.4-1.5L63.4.2C61.2-.2 58.3 0 55.7.2L1.8 4.2C.5 4.4 .2 5.1 .6 5.9L6 4.8zm2.4 9.2v57.8c0 3.1 1.5 4.3 5 4.1l63-3.6c3.5-.2 3.9-2.4 3.9-5V9.6c0-2.6-1-4-3.3-3.8L11.7 9.4c-2.5.2-3.3 1.5-3.3 4.6zm62.1 2.4c.4 1.7 0 3.4-1.7 3.6l-2.8.5v41.3c-2.4 1.3-4.7 2-6.6 2-3.1 0-3.9-.9-6.2-3.7L36.4 36.4v28.3l5.9 1.3s0 3.4-4.7 3.4l-13-.7c-.4-.9 0-3.1 1.3-3.5l3.4-.9V24.3L24.5 24c-.4-1.7.6-4.1 3.3-4.3l14-.9 19.2 29.4V21.2l-5-.5c-.4-2.1 1.2-3.6 3.1-3.8l13.4-.3z"/></svg>
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
