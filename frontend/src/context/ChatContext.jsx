import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../services/api';

const ChatContext = createContext(null);

export function ChatProvider({ children }) {
  const [messages, setMessages] = useState(() => {
    try {
      const stored = localStorage.getItem('chat_messages');
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });
  const [isLoading, setIsLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [llmStatus, setLlmStatus] = useState(null); // {type,message}

  useEffect(() => {
    try {
      const capped = messages.slice(-200);
      localStorage.setItem('chat_messages', JSON.stringify(capped));
    } catch {
      /* ignore */
    }
  }, [messages]);

  const sendMessage = useCallback(async (text, voiceAudio = null) => {
    setIsLoading(true);
    setLlmStatus(null);
    const userMsg = { role: 'user', content: text || '(Message)' };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const payload = { query: text, voice_audio: voiceAudio };
      const response = await api.post('/chat/query', payload);
      const { response: aiText, sources_used } = response.data;
      setMessages((prev) => [...prev, { role: 'assistant', content: aiText, sources_used }]);
    } catch (error) {
      console.error('Chat error:', error);
      const detail =
        error.response?.data?.detail ||
        (error.response?.status === 503 ? 'Model is temporarily unavailable. Please retry shortly.' : 'Error processing request.');
      setMessages((prev) => [...prev, { role: 'assistant', content: detail, error: true }]);
      if (error.response?.status === 503) {
        setLlmStatus({ type: 'warning', message: 'LLM is temporarily unavailable. Please retry in a few seconds.' });
      } else {
        setLlmStatus({ type: 'error', message: 'Chat request failed. Please try again.' });
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    try {
      localStorage.removeItem('chat_messages');
    } catch {
      /* ignore */
    }
  }, []);

  const uploadDoc = useCallback(async (file) => {
    setIsUploading(true);
    setUploadStatus(null);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await api.post('/docs/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const jobId = res.data?.job_id;
      const message = jobId
        ? `Uploaded ${file.name}. Ingestion job: ${jobId.slice(0, 8)}...`
        : `Uploaded ${file.name}`;
      setUploadStatus({ type: 'success', message });
      // Optionally track job IDs for polling later
      if (jobId) {
        const existing = JSON.parse(localStorage.getItem('doc_jobs') || '[]');
        existing.unshift({ jobId, filename: file.name, createdAt: Date.now() });
        localStorage.setItem('doc_jobs', JSON.stringify(existing.slice(0, 10)));
      }
    } catch (error) {
      setUploadStatus({
        type: 'error',
        message: error.response?.data?.detail || 'Upload failed',
      });
    } finally {
      setIsUploading(false);
    }
  }, []);

  const clearDocs = useCallback(async () => {
    await api.delete('/docs/clear');
    setUploadStatus({ type: 'success', message: 'Knowledge base cleared' });
  }, []);

  return (
    <ChatContext.Provider
      value={{
        messages,
        isLoading,
        isUploading,
      uploadStatus,
      llmStatus,
      sendMessage,
      clearMessages,
      uploadDoc,
      clearDocs,
      setUploadStatus,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChat must be used within ChatProvider');
  return ctx;
}
