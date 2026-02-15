import React, { useEffect, useRef } from 'react';
import { Copy } from 'lucide-react';

export default function TranscriptPanel({ transcripts, interimTranscript, isRecording }) {
    const bottomRef = useRef(null);
    const containerRef = useRef(null);

    useEffect(() => {
        if (isRecording) {
            if (bottomRef.current) {
                bottomRef.current.scrollIntoView({ behavior: 'smooth' });
            }
        }
    }, [transcripts, isRecording]);

    const handleCopy = () => {
        if (!transcripts) return;
        const text = transcripts.map(t => `[${t.timestamp || ''}] ${t.text}`).join('\n');
        navigator.clipboard.writeText(text);
    };

    return (
        <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden flex flex-col h-full shadow-sm">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-white sticky top-0 z-10">
                <h3 className="font-semibold text-slate-900 flex items-center gap-2">
                    {isRecording && (
                        <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse shadow-[0_0_8px_rgba(239,68,68,0.6)]" />
                    )}
                    Live Transcript
                </h3>
                <button
                    onClick={handleCopy}
                    className="p-2 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-800 transition-colors"
                    title="Copy to clipboard"
                >
                    <Copy size={18} />
                </button>
            </div>

            <div
                ref={containerRef}
                className="flex-1 overflow-y-auto p-4 space-y-4 font-mono text-sm custom-scrollbar relative"
            >
                {(!transcripts || transcripts.length === 0) && !interimTranscript ? (
                    <div className="absolute inset-0 flex items-center justify-center text-slate-400 italic">
                        Waiting for speech...
                    </div>
                ) : (
                    <>
                        {transcripts.map((item, index) => (
                            <div key={index} className="flex gap-4 group hover:bg-amber-50 p-2 rounded-lg transition-colors -mx-2">
                                <span className="text-slate-500 text-xs mt-1 shrink-0 w-16 text-right font-medium select-none">
                                    {item.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                </span>
                                <div className="flex-1">
                                    {item.speaker !== undefined && (
                                        <span className="text-amber-700 text-xs font-bold mr-2 uppercase tracking-wide bg-amber-100 px-1.5 py-0.5 rounded">
                                            Speaker {item.speaker}
                                        </span>
                                    )}
                                    <span className="text-slate-700 leading-relaxed">{item.text}</span>
                                </div>
                            </div>
                        ))}
                        {interimTranscript && (
                            <div className="flex gap-4 p-2 rounded-lg -mx-2 bg-amber-50 border border-amber-100">
                                <span className="text-slate-500 text-xs mt-1 shrink-0 w-16 text-right font-medium select-none">
                                    now
                                </span>
                                <div className="flex-1">
                                    <span className="text-slate-500 leading-relaxed italic">{interimTranscript}</span>
                                </div>
                            </div>
                        )}
                    </>
                )}
                <div ref={bottomRef} className="h-4" />
            </div>
        </div>
    );
}
