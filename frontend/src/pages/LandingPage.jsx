import { Link, Navigate } from 'react-router-dom';
import { Mic, FileText, MessageSquare } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function LandingPage() {
    const { user, loading } = useAuth();

    if (loading) {
        return (
            <div className="min-h-[calc(100vh-64px)] flex items-center justify-center text-slate-500">
                <div className="animate-pulse">Loading...</div>
            </div>
        );
    }

    if (user) {
        return <Navigate to="/meeting" replace />;
    }

    return (
        <div className="min-h-[calc(100vh-64px)] flex flex-col items-center justify-center">

            {/* Hero Section */}
            <div className="text-center max-w-4xl px-4 sm:px-6 lg:px-8 py-20">
                <h1 className="text-5xl md:text-7xl font-bold tracking-tight mb-6 bg-gradient-to-r from-slate-900 via-slate-700 to-amber-700 text-transparent bg-clip-text">
                    Your Intelligent Meeting & Document Assistant
                </h1>
                <p className="text-xl md:text-2xl text-slate-600 mb-10 max-w-2xl mx-auto">
                    Capture meetings with real-time transcription, chat with your documents, and get AI-powered summaries instantly.
                </p>

                <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                    <Link
                        to="/signup"
                        className="px-8 py-4 bg-slate-900 hover:bg-slate-700 text-white rounded-xl font-semibold text-lg transition-all shadow-md"
                    >
                        Start for Free
                    </Link>
                    <Link
                        to="/login"
                        className="px-8 py-4 bg-amber-100 hover:bg-amber-200 text-amber-900 rounded-xl font-semibold text-lg transition-all"
                    >
                        Log In
                    </Link>
                </div>
            </div>

            {/* Features Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-7xl px-4 py-20 w-full">
                <FeatureCard
                    icon={Mic}
                    title="Live Transcription"
                    desc="Real-time speech-to-text with high accuracy and speaker diarization."
                />
                <FeatureCard
                    icon={FileText}
                    title="Smart Summaries"
                    desc="Automated meeting minutes, action items, and periodic updates."
                />
                <FeatureCard
                    icon={MessageSquare}
                    title="Interactive Chat"
                    desc="Chat with your documents and past meetings using AI context."
                />
            </div>

        </div>
    );
}

function FeatureCard({ icon: Icon, title, desc }) {
    return (
        <div className="p-6 rounded-2xl bg-white border border-slate-200 hover:border-amber-300 transition-colors shadow-sm">
            <div className="w-12 h-12 bg-amber-100 rounded-lg flex items-center justify-center mb-4">
                <Icon className="text-amber-700" size={24} />
            </div>
            <h3 className="text-xl font-semibold text-slate-900 mb-2">{title}</h3>
            <p className="text-slate-600">{desc}</p>
        </div>
    );
}
