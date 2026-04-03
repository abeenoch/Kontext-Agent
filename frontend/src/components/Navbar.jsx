import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Mic, MessageSquare, LogOut } from 'lucide-react';
import clsx from 'clsx';
import logoSrc from '../assets/logo-k.svg';

export default function Navbar() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    const NavLink = ({ to, icon: Icon, children }) => (
        <Link
            to={to}
            className={clsx(
                "flex items-center space-x-2 px-3 py-2 rounded-xl transition-all",
                "hover:bg-amber-100 text-slate-600 hover:text-slate-900"
            )}
        >
            <Icon size={18} />
            <span>{children}</span>
        </Link>
    );

    return (
        <nav className="border-b border-slate-200 bg-white/90 backdrop-blur-sm sticky top-0 z-50">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="flex items-center justify-between h-16">

                    {/* Logo */}
                    <Link to="/" className="flex items-center space-x-2 font-bold text-xl text-slate-900">
                        <img src={logoSrc} alt="Kontext" className="w-8 h-8 rounded-lg shadow-sm" />
                        <span>Kontext</span>
                    </Link>

                    {/* User Navigation */}
                    {user && (
                        <div className="hidden md:flex items-center space-x-4">
                            <NavLink to="/meeting" icon={Mic}>Meeting</NavLink>
                            <NavLink to="/chat" icon={MessageSquare}>Chat</NavLink>
                        </div>
                    )}

                    {/* Auth Buttons */}
                    <div className="flex items-center space-x-4">
                        {user ? (
                            <div className="flex items-center space-x-4">
                                <span className="text-sm text-slate-400 hidden sm:block">
                                    {user.display_name}
                                </span>
                                <button
                                    onClick={handleLogout}
                                    className="p-2 rounded-full hover:bg-rose-50 text-slate-500 hover:text-rose-600 transition-colors"
                                    title="Logout"
                                >
                                    <LogOut size={20} />
                                </button>
                            </div>
                        ) : (
                            <div className="flex items-center space-x-4">
                                <Link
                                    to="/login"
                                    className="text-slate-600 hover:text-slate-900 font-medium"
                                >
                                    Login
                                </Link>
                                <Link
                                    to="/signup"
                                    className="bg-slate-900 hover:bg-slate-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
                                >
                                    Get Started
                                </Link>
                            </div>
                        )}
                    </div>

                </div>
            </div>
        </nav>
    );
}
