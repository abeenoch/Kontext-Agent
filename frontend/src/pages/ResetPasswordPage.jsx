import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Lock, ArrowLeft, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function ResetPasswordPage() {
    const { resetPassword } = useAuth();
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();

    const [token, setToken] = useState('');
    const [password, setPassword] = useState('');
    const [confirm, setConfirm] = useState('');
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        const t = searchParams.get('token') || '';
        setToken(t);
        if (!t) {
            setError('Reset link is invalid or missing. Please request a new one.');
        }
    }, [searchParams]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (loading) return;
        setError('');
        setSuccess('');

        if (!token) {
            setError('Reset link is invalid or missing. Please request a new one.');
            return;
        }

        if (password.length < 8) {
            setError('Password must be at least 8 characters.');
            return;
        }

        if (password !== confirm) {
            setError('Passwords do not match.');
            return;
        }

        setLoading(true);
        const result = await resetPassword(token, password);
        setLoading(false);
        if (result.success) {
            setSuccess('Password updated. You can sign in with your new password.');
            setPassword('');
            setConfirm('');
            setTimeout(() => navigate('/login'), 1200);
        } else {
            setError(result.message);
        }
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
                    <h2 className="text-3xl font-bold text-slate-900 mb-2">Set a new password</h2>
                    <p className="text-slate-600">Choose a strong password to secure your account.</p>
                </div>

                {error && (
                    <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-lg flex items-center gap-2 mb-6">
                        <AlertCircle size={18} />
                        <span className="text-sm">{error}</span>
                    </div>
                )}

                {success && (
                    <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 p-3 rounded-lg flex items-center gap-2 mb-6">
                        <CheckCircle2 size={18} />
                        <span className="text-sm">{success}</span>
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-6">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1.5">New password</label>
                        <div className="relative">
                            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={20} />
                            <input
                                type="password"
                                required
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="w-full bg-white border border-slate-300 rounded-lg py-2.5 pl-10 pr-4 text-slate-900 focus:ring-2 focus:ring-amber-400 focus:border-amber-300 outline-none transition-all placeholder:text-slate-400"
                                placeholder="••••••••"
                            />
                        </div>
                        <p className="mt-1 text-xs text-slate-500">Must be at least 8 characters.</p>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1.5">Confirm password</label>
                        <div className="relative">
                            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={20} />
                            <input
                                type="password"
                                required
                                value={confirm}
                                onChange={(e) => setConfirm(e.target.value)}
                                className="w-full bg-white border border-slate-300 rounded-lg py-2.5 pl-10 pr-4 text-slate-900 focus:ring-2 focus:ring-amber-400 focus:border-amber-300 outline-none transition-all placeholder:text-slate-400"
                                placeholder="••••••••"
                            />
                        </div>
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full bg-slate-900 hover:bg-slate-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-lg transition-colors"
                    >
                        {loading ? 'Updating...' : 'Update password'}
                    </button>
                </form>
            </div>
        </div>
    );
}
