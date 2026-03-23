import { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // Check for stored token and user data on load
        const token = localStorage.getItem('token');
        const savedUser = localStorage.getItem('user');

        if (token && savedUser) {
            setUser(JSON.parse(savedUser));
        }
        setLoading(false);
    }, []);

    const login = async (email, password) => {
        try {
            const response = await api.post('/auth/login', { email, password });
            const { access_token, user_id, display_name } = response.data;

            const userData = { user_id, display_name, email };

            localStorage.setItem('token', access_token);
            localStorage.setItem('user', JSON.stringify(userData));
            setUser(userData);
            return { success: true };
        } catch (error) {
            console.error('Login failed:', error);
            return {
                success: false,
                message: error.response?.data?.detail || 'Login failed'
            };
        }
    };

    const signup = async (email, password, displayName) => {
        try {
            const response = await api.post('/auth/signup', {
                email,
                password,
                display_name: displayName
            });
            const { access_token, user_id, display_name } = response.data;

            const userData = { user_id, display_name, email };

            localStorage.setItem('token', access_token);
            localStorage.setItem('user', JSON.stringify(userData));
            setUser(userData);
            return { success: true };
        } catch (error) {
            console.error('Signup failed:', error);
            return {
                success: false,
                message: error.response?.data?.detail || 'Signup failed'
            };
        }
    };

    const requestPasswordReset = async (email) => {
        try {
            const response = await api.post('/auth/forgot-password', { email });
            // Backend may return reset_token when email service isn't configured
            return {
                success: true,
                resetToken: response.data?.reset_token || null
            };
        } catch (error) {
            console.error('Forgot password failed:', error);
            return {
                success: false,
                message: error.response?.data?.detail || 'Unable to start password reset'
            };
        }
    };

    const resetPassword = async (token, newPassword) => {
        try {
            await api.post('/auth/reset-password', { token, new_password: newPassword });
            return { success: true };
        } catch (error) {
            console.error('Reset password failed:', error);
            return {
                success: false,
                message: error.response?.data?.detail || 'Reset link is invalid or expired'
            };
        }
    };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setUser(null);
    // Notify other contexts (e.g., Meeting) to cleanup
    window.dispatchEvent(new Event('app:logout'));
  };

    return (
        <AuthContext.Provider
            value={{
                user,
                login,
                signup,
                logout,
                loading,
                requestPasswordReset,
                resetPassword
            }}
        >
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
