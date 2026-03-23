import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../services/api';

const ChatContext = createContext(null);

const newTab = (name = 'New chat') => ({
  id: (crypto?.randomUUID ? crypto.randomUUID() : `tab-${Date.now()}`),
  name,
  createdAt: Date.now(),
});

export function ChatProvider({ children }) {
  const [messagesByTab, setMessagesByTab] = useState(() => {
    try {
      const stored = localStorage.getItem('chat_messages_v2');
      return stored ? JSON.parse(stored) : {};
    } catch {
      return {};
    }
  });
  const [isLoading, setIsLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [llmStatus, setLlmStatus] = useState(null); // {type,message}
  const [tabs, setTabs] = useState(() => {
    try {
      const stored = localStorage.getItem('chat_tabs');
      const parsed = stored ? JSON.parse(stored) : [];
      if (parsed.length) return parsed;
    } catch {
      /* ignore */
    }
    const initial = [newTab('Chat 1')];
    localStorage.setItem('chat_tabs', JSON.stringify(initial));
    localStorage.setItem('chat_active_tab', initial[0].id);
    return initial;
  });
  const [activeTabId, setActiveTabId] = useState(() => {
    try {
      const stored = localStorage.getItem('chat_active_tab');
      return stored || null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem('chat_messages_v2', JSON.stringify(messagesByTab));
    } catch {
      /* ignore */
    }
  }, [messagesByTab]);

  // Persist tabs and active tab
  useEffect(() => {
    try {
      localStorage.setItem('chat_tabs', JSON.stringify(tabs));
    } catch {
      /* ignore */
    }
  }, [tabs]);

  useEffect(() => {
    if (!activeTabId && tabs.length) {
      setActiveTabId(tabs[0].id);
      return;
    }
    try {
      if (activeTabId) localStorage.setItem('chat_active_tab', activeTabId);
    } catch {
      /* ignore */
    }
  }, [activeTabId, tabs]);

  const ensureActiveTab = () => {
    if (activeTabId) return activeTabId;
    const first = tabs[0] || newTab('Chat 1');
    setTabs([first]);
    setActiveTabId(first.id);
    return first.id;
  };

  const activeMessages = messagesByTab[activeTabId] || [];

  const sendMessage = useCallback(async (text, voiceAudio = null) => {
    setIsLoading(true);
    setLlmStatus(null);
    const tabId = ensureActiveTab();
    const userMsg = { role: 'user', content: text || '(Message)' };
    setMessagesByTab((prev) => ({
      ...prev,
      [tabId]: [...(prev[tabId] || []), userMsg],
    }));

    try {
      const payload = { query: text, voice_audio: voiceAudio, tab_id: tabId };
      const response = await api.post('/chat/query', payload);
      const { response: aiText, sources_used } = response.data;
      setMessagesByTab((prev) => ({
        ...prev,
        [tabId]: [...(prev[tabId] || []), { role: 'assistant', content: aiText, sources_used }],
      }));
    } catch (error) {
      console.error('Chat error:', error);
      const detail =
        error.response?.data?.detail ||
        (error.response?.status === 503 ? 'Model is temporarily unavailable. Please retry shortly.' : 'Error processing request.');
      setMessagesByTab((prev) => ({
        ...prev,
        [ensureActiveTab()]: [...(prev[ensureActiveTab()] || []), { role: 'assistant', content: detail, error: true }],
      }));
      if (error.response?.status === 503) {
        setLlmStatus({ type: 'warning', message: 'LLM is temporarily unavailable. Please retry in a few seconds.' });
      } else {
        setLlmStatus({ type: 'error', message: 'Chat request failed. Please try again.' });
      }
    } finally {
      setIsLoading(false);
    }
  }, [ensureActiveTab]);

  const clearMessages = useCallback(() => {
    const tabId = ensureActiveTab();
    setMessagesByTab((prev) => {
      const next = { ...prev };
      next[tabId] = [];
      return next;
    });
    try {
      const stored = JSON.parse(localStorage.getItem('chat_messages_v2') || '{}');
      stored[tabId] = [];
      localStorage.setItem('chat_messages_v2', JSON.stringify(stored));
    } catch {
      /* ignore */
    }
  }, [ensureActiveTab]);

  const uploadDoc = useCallback(async (file) => {
    setIsUploading(true);
    setUploadStatus(null);
    const tabId = ensureActiveTab();
    const formData = new FormData();
    formData.append('file', file);
    formData.append('tab_id', tabId);
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
        existing.unshift({ jobId, filename: file.name, createdAt: Date.now(), tabId });
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
  }, [ensureActiveTab]);

  const clearDocs = useCallback(async () => {
    const tabId = ensureActiveTab();
    await api.delete(`/docs/clear?tab_id=${encodeURIComponent(tabId)}`);
    setUploadStatus({ type: 'success', message: 'Knowledge base cleared' });
  }, [ensureActiveTab]);

  const addTab = useCallback((name) => {
    const tab = newTab(name || `Chat ${tabs.length + 1}`);
    setTabs((prev) => [tab, ...prev]);
    setActiveTabId(tab.id);
    return tab.id;
  }, [tabs]);

  const activateTab = useCallback((id) => {
    setActiveTabId(id);
  }, []);

  const deleteTab = useCallback(async (id) => {
    // Clear backend vector space for this tab
    try {
      await api.delete(`/docs/clear?tab_id=${encodeURIComponent(id)}`);
    } catch {
      /* ignore backend clear errors */
    }

    setTabs((prev) => {
      const remaining = prev.filter((t) => t.id !== id);
      // Determine next active: same index if possible, otherwise previous, otherwise new
      let nextActiveId = activeTabId;
      if (id === activeTabId) {
        const deletedIndex = prev.findIndex((t) => t.id === id);
        const candidate = remaining[deletedIndex] || remaining[deletedIndex - 1] || null;
        if (candidate) {
          nextActiveId = candidate.id;
        } else {
          const fresh = newTab('Chat 1');
          nextActiveId = fresh.id;
          remaining.unshift(fresh);
          setMessagesByTab((mPrev) => ({ ...mPrev, [fresh.id]: [] }));
        }
        setActiveTabId(nextActiveId);
      }
      return remaining.length ? remaining : [newTab('Chat 1')];
    });

    // Drop messages for the tab
    setMessagesByTab((prev) => {
      const copy = { ...prev };
      delete copy[id];
      return copy;
    });

    // Drop local job tracking for the tab
    try {
      const jobs = JSON.parse(localStorage.getItem('doc_jobs') || '[]').filter((j) => j.tabId !== id);
      localStorage.setItem('doc_jobs', JSON.stringify(jobs));
    } catch {
      /* ignore */
    }
  }, [activeTabId]);

  return (
    <ChatContext.Provider
      value={{
        messages: activeMessages,
        isLoading,
        isUploading,
        uploadStatus,
        llmStatus,
        tabs,
        activeTabId,
      sendMessage,
      clearMessages,
      uploadDoc,
      clearDocs,
      setUploadStatus,
      addTab,
      activateTab,
      deleteTab,
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
