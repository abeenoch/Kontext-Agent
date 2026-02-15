import { useState, useRef, useCallback, useEffect } from 'react';

export function useWebSocket(url, onMessage) {
    const [isConnected, setIsConnected] = useState(false);
    const [error, setError] = useState(null);
    const wsRef = useRef(null);
    const pendingMessagesRef = useRef([]);
    const shouldReconnectRef = useRef(false);
    const reconnectTimerRef = useRef(null);

    const connect = useCallback((overrideUrl = null) => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            return;
        }
        try {
            shouldReconnectRef.current = true;
            const ws = new WebSocket(overrideUrl || url);
            wsRef.current = ws;

            ws.onopen = () => {
                console.log('WebSocket connected');
                setIsConnected(true);
                setError(null);

                while (pendingMessagesRef.current.length > 0) {
                    ws.send(pendingMessagesRef.current.shift());
                }
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    onMessage(data);
                } catch (e) {
                    console.error('WebSocket message parse error:', e);
                }
            };

            ws.onerror = (e) => {
                console.error('WebSocket error:', e);
                setError('Connection error');
            };

            ws.onclose = () => {
                console.log('WebSocket closed');
                setIsConnected(false);
                wsRef.current = null;
                if (shouldReconnectRef.current) {
                    reconnectTimerRef.current = setTimeout(() => {
                        connect(overrideUrl);
                    }, 1000);
                }
            };
        } catch (e) {
            console.error('WebSocket connection failed:', e);
            setError('Failed to connect');
        }
    }, [url, onMessage]);

    const sendMessage = useCallback((message, options = {}) => {
        const {
            dropIfDisconnected = false,
            maxPending = 200
        } = options;

        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(message);
        } else {
            if (dropIfDisconnected) {
                return;
            }
            pendingMessagesRef.current.push(message);
            if (pendingMessagesRef.current.length > maxPending) {
                pendingMessagesRef.current.shift();
            }
        }
    }, []);

    const disconnect = useCallback(() => {
        shouldReconnectRef.current = false;
        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
        }
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        pendingMessagesRef.current = [];
        setIsConnected(false);
    }, []);

    useEffect(() => {
        return () => {
            disconnect();
        };
    }, [disconnect]);

    return { isConnected, error, connect, disconnect, sendMessage };
}
