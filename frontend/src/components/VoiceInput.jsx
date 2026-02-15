import { useState, useRef } from 'react';
import { Mic, Square, Loader2, Waves } from 'lucide-react';
import { useAudioCapture } from '../hooks/useAudioCapture';

export default function VoiceInput({ onAudioSubmit, disabled }) {
    const { isRecording, startCapture, stopCapture } = useAudioCapture();
    const [isProcessing, setIsProcessing] = useState(false);
    const chunksRef = useRef([]);
    const speechDetectedRef = useRef(false);
    const silenceMsRef = useRef(0);
    const lastChunkTsRef = useRef(0);
    const autoStoppingRef = useRef(false);

    const SILENCE_THRESHOLD = 300;
    const SILENCE_MS_TO_AUTO_STOP = 1200;

    const decodePcmPeak = (base64Chunk) => {
        const bytes = Uint8Array.from(atob(base64Chunk), c => c.charCodeAt(0));
        let peak = 0;
        for (let i = 0; i + 1 < bytes.length; i += 2) {
            const sample = (bytes[i + 1] << 8) | bytes[i];
            const signed = sample > 0x7FFF ? sample - 0x10000 : sample;
            const abs = Math.abs(signed);
            if (abs > peak) peak = abs;
        }
        return peak;
    };

    const combineChunksToBase64 = () => {
        const allBytes = chunksRef.current.map(chunk =>
            Uint8Array.from(atob(chunk), c => c.charCodeAt(0))
        );

        const totalLength = allBytes.reduce((acc, curr) => acc + curr.length, 0);
        const combined = new Uint8Array(totalLength);

        let offset = 0;
        for (const bytes of allBytes) {
            combined.set(bytes, offset);
            offset += bytes.length;
        }

        let binary = '';
        for (let i = 0; i < combined.byteLength; i++) {
            binary += String.fromCharCode(combined[i]);
        }
        return window.btoa(binary);
    };

    const finalizeSubmission = async () => {
        if (autoStoppingRef.current) return;
        autoStoppingRef.current = true;
        stopCapture();
        setIsProcessing(true);

        try {
            if (!chunksRef.current.length) return;
            const finalBase64 = combineChunksToBase64();
            onAudioSubmit(finalBase64);
        } catch (e) {
            console.error('Error processing audio', e);
        } finally {
            setIsProcessing(false);
            autoStoppingRef.current = false;
        }
    };

    const handleStart = async () => {
        chunksRef.current = [];
        speechDetectedRef.current = false;
        silenceMsRef.current = 0;
        lastChunkTsRef.current = performance.now();
        autoStoppingRef.current = false;

        const started = await startCapture((base64Chunk) => {
            chunksRef.current.push(base64Chunk);

            const now = performance.now();
            const elapsed = now - lastChunkTsRef.current;
            lastChunkTsRef.current = now;

            const peak = decodePcmPeak(base64Chunk);
            const isSpeech = peak > SILENCE_THRESHOLD;

            if (isSpeech) {
                speechDetectedRef.current = true;
                silenceMsRef.current = 0;
                return;
            }

            if (speechDetectedRef.current) {
                silenceMsRef.current += elapsed;
                if (silenceMsRef.current >= SILENCE_MS_TO_AUTO_STOP) {
                    finalizeSubmission();
                }
            }
        });

        if (!started) {
            console.error('Failed to start recording');
        }
    };

    const handleStop = async () => finalizeSubmission();

    if (isRecording) {
        return (
            <button
                onClick={handleStop}
                disabled={disabled}
                className="p-3 bg-rose-500 hover:bg-rose-600 text-white rounded-2xl transition-all shadow-md flex items-center gap-2"
                title="Stop recording and send"
            >
                <Square size={20} fill="currentColor" />
                <Waves size={18} className="animate-pulse" />
            </button>
        );
    }

    return (
        <button
            onClick={handleStart}
            disabled={disabled || isProcessing}
            className={`p-3 rounded-full transition-all ${disabled
                    ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
                    : 'bg-amber-500 hover:bg-amber-600 text-white shadow-md'
                }`}
            title="Voice input (auto-sends on silence)"
        >
            {isProcessing ? <Loader2 size={20} className="animate-spin" /> : <Mic size={20} />}
        </button>
    );
}
