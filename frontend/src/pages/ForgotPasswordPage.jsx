import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Mail, ArrowLeft, AlertCircle, CheckCircle2, Copy } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function ForgotPasswordPage() {
    const { requestPasswordReset } = useAuth();
    const [email, setEmail] = useState('');
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [devToken, setDevToken] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setSuccess('');
        setDevToken('');

        const result = await requestPasswordReset(email);
        if (result.success) {
            setSuccess('If an account exists, we sent a reset link to your email.');
            if (result.resetToken) {
                setDevToken(result.resetToken);
            }
        } else {
            setError(result.message);
        }
    };

    const copyToken = () => {
        if (!devToken) return;
        navigator.clipboard.writeText(devToken).catch(() => {});
    };

    return (
        <div className="min-h-[calc(100vh-64px)] flex items-center justify-center px-4">
            <div className="max-w-md w-full bg-white border border-slate-200 rounded-2xl p-8 shadow-xl shadow-slate-200/70">
                <div className="flex items-center gap-2 text-sm text-slate-600 mb-6">
                    <ArrowLeft size={16} className="text-slate-400" />
                    <Link to="/login" className="text-amber-700 hover:text-amber-800 font-medium">
                        Back to sign in
                    </Link>
                </div>

                <div className="text-center mb-6">
                    <h2 className="text-3xl font-bold text-slate-900 mb-2">Forgot password?</h2>
                    <p className="text-slate-600">We’ll email you a link to reset it.</p>
                </div>

                {error && (
                    <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-lg flex items-center gap-2 mb-6">
                        <AlertCircle size={18} />
                        <span className="text-sm">{error}</span>
                    </div>
                )}

                {success && (
                    <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 p-3 rounded-lg flex items-start gap-2 mb-6">
                        <CheckCircle2 size={18} className="mt-0.5" />
                        <span className="text-sm">{success}</span>
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-6">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1.5">Email Address</label>
                        <div className="relative">
                            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={20} />
                            <input
                                type="email"
                                required
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full bg-white border border-slate-300 rounded-lg py-2.5 pl-10 pr-4 text-slate-900 focus:ring-2 focus:ring-amber-400 focus:border-amber-300 outline-none transition-all placeholder:text-slate-400"
                                placeholder="you@example.com"
                            />
                        </div>
                    </div>

                    <button
                        type="submit"
                        className="w-full bg-slate-900 hover:bg-slate-700 text-white font-semibold py-2.5 rounded-lg transition-colors"
                    >
                        Send reset link
                    </button>
                </form>

                {devToken && (
                    <div className="mt-6 bg-slate-50 border border-slate-200 rounded-xl p-4">
                        <p className="text-xs font-semibold text-slate-700 mb-2">Dev reset token (SMTP not configured)</p>
                        <div className="flex items-center gap-2">
                            <code className="flex-1 text-xs break-all text-slate-800 bg-white border border-slate-200 rounded px-2 py-1">
                                {devToken}
                            </code>
                            <button
                                type="button"
                                onClick={copyToken}
                                className="flex items-center gap-1 text-amber-700 hover:text-amber-800 text-xs font-semibold"
                            >
                                <Copy size={14} /> Copy
                            </button>
                        </div>
                        <p className="text-[11px] text-slate-500 mt-2">
                            Use this token on the reset page for local testing.
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
