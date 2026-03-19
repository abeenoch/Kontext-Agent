import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { MeetingProvider } from './context/MeetingContext';
import { ChatProvider } from './context/ChatContext';
import Navbar from './components/Navbar';
import LandingPage from './pages/LandingPage';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import MeetingPage from './pages/MeetingPage';
import DocsPage from './pages/DocsPage';
import ChatPage from './pages/ChatPage';

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-white text-slate-500">
        <div className="animate-pulse">Loading...</div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" />;
  }

  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <MeetingProvider>
        <ChatProvider>
          <div className="min-h-screen bg-white text-slate-900 font-sans flex flex-col">
            <Navbar />
            <main className="flex-1 relative">
              <Routes>
                <Route path="/" element={<LandingPage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/signup" element={<SignupPage />} />

                {/* Protected Routes */}
                <Route path="/meeting" element={
                  <ProtectedRoute>
                    <MeetingPage />
                  </ProtectedRoute>
                } />
                <Route path="/docs" element={
                  <ProtectedRoute>
                    <DocsPage />
                  </ProtectedRoute>
                } />
                <Route path="/chat" element={
                  <ProtectedRoute>
                    <ChatPage />
                  </ProtectedRoute>
                } />

                {/* Catch all redirect to home or login */}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </main>
          </div>
        </ChatProvider>
      </MeetingProvider>
    </AuthProvider>
  );
}
