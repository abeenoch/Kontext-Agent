import { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Loader2, Volume2, VolumeX } from 'lucide-react';
import VoiceInput from './VoiceInput';

export default function ChatPanel({
    messages,
    onSendMessage,
    isLoading,
    placeholder,
    enableVoiceInput = true,
    enableVoiceReply = true,
}) {
    const [input, setInput] = useState('');
    const [voiceReplyEnabled, setVoiceReplyEnabled] = useState(enableVoiceReply);
    const bottomRef = useRef(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    useEffect(() => {
        setVoiceReplyEnabled(enableVoiceReply);
    }, [enableVoiceReply]);

    useEffect(() => {
        const last = messages[messages.length - 1];
        if (!voiceReplyEnabled || !last || last.role !== 'assistant') return;
        if (!('speechSynthesis' in window)) return;

        const plainText = last.content
            .replace(/[#*_`>\-\[\]\(\)]/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();

        if (!plainText) return;

        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(plainText);
        utterance.rate = 1;
        utterance.pitch = 1;
        window.speechSynthesis.speak(utterance);

        return () => {
            window.speechSynthesis.cancel();
        };
    }, [messages, voiceReplyEnabled]);

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!input.trim() || isLoading) return;
        onSendMessage(input);
        setInput('');
    };

    const handleVoiceInput = (base64Audio) => {
        onSendMessage('', base64Audio);
    };

    return (
        <div className="flex flex-col h-full bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-lg shadow-slate-200/70">

            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto p-4 space-y-6 custom-scrollbar bg-gradient-to-b from-white to-amber-50/40">
                {messages.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-slate-500">
                        <Bot size={48} className="mb-4 text-amber-500/70" />
                        <p className="text-sm font-medium">
                            {enableVoiceInput ? 'Ask anything or use voice input' : 'Ask anything'}
                        </p>
                    </div>
                ) : (
                    messages.map((msg, idx) => (
                        <div
                            key={idx}
                            className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                        >
                            <div className={`
                w-8 h-8 rounded-full flex items-center justify-center shrink-0
                ${msg.role === 'user' ? 'bg-amber-500' : 'bg-slate-700'}
              `}>
                                {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
                            </div>

                            <div className={`
                max-w-[80%] rounded-2xl px-5 py-3 text-sm leading-relaxed
                ${msg.role === 'user'
                                    ? 'bg-amber-500 text-white rounded-tr-none'
                                    : 'bg-slate-100 text-slate-800 rounded-tl-none border border-slate-200'}
              `}>
                                <p className="whitespace-pre-line break-words">{msg.content}</p>
                                {msg.sources && (
                                    <div className="mt-2 pt-2 border-t border-slate-300 text-xs text-slate-500 flex items-center gap-1">
                                        Sources used
                                    </div>
                                )}
                            </div>
                        </div>
                    ))
                )}
                {isLoading && (
                    <div className="flex gap-4">
                        <div className="w-8 h-8 rounded-full bg-slate-700 text-white flex items-center justify-center shrink-0">
                            <Bot size={16} />
                        </div>
                        <div className="bg-slate-100 border border-slate-200 rounded-2xl rounded-tl-none px-5 py-4 flex items-center gap-2">
                            <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                            <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                            <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                        </div>
                    </div>
                )}
                <div ref={bottomRef} />
            </div>

            {/* Input Area */}
            <div className="p-4 bg-white/90 border-t border-slate-200">
                <form onSubmit={handleSubmit} className="flex items-end gap-3 max-w-4xl mx-auto relative">
                    <div className="relative flex-1">
                        <textarea
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            placeholder={placeholder || "Type a message..."}
                            disabled={isLoading}
                            rows={1}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' && !e.shiftKey) {
                                    e.preventDefault();
                                    handleSubmit(e);
                                }
                            }}
                            className="w-full bg-white border border-slate-300 rounded-2xl py-3 pl-4 pr-14 text-slate-900 focus:ring-2 focus:ring-amber-400 focus:border-amber-300 outline-none resize-none custom-scrollbar max-h-32 min-h-[48px]"
                        />
                        {enableVoiceInput && (
                            <div className="absolute right-2 bottom-2">
                                <VoiceInput onAudioSubmit={handleVoiceInput} disabled={isLoading} />
                            </div>
                        )}
                    </div>

                    <button
                        type="submit"
                        disabled={!input.trim() || isLoading}
                        className="p-3 bg-slate-900 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-full transition-all shadow-md mb-px"
                    >
                        <Send size={20} className={isLoading ? 'opacity-0' : ''} />
                        {isLoading && <Loader2 size={20} className="absolute animate-spin" />}
                    </button>
                    {enableVoiceReply && (
                        <button
                            type="button"
                            onClick={() => setVoiceReplyEnabled((prev) => !prev)}
                            className="p-3 rounded-full border border-slate-300 text-slate-600 hover:bg-slate-100 transition-colors mb-px"
                            title={voiceReplyEnabled ? 'Disable voice replies' : 'Enable voice replies'}
                        >
                            {voiceReplyEnabled ? <Volume2 size={20} /> : <VolumeX size={20} />}
                        </button>
                    )}
                </form>
            </div>

        </div>
    );
}
