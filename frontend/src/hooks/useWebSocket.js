import { useState, useRef, useCallback, useEffect } from 'react';

/**
 * WebSocket hook with queued sends, exponential backoff reconnect,
 * and optional lifecycle callbacks.
 *
 * @param {string} url - base WebSocket URL
 * @param {Function} onMessage - handler for JSON payloads
 * @param {Object} options
 * @param {Function} options.onOpen - called after socket opens
 * @param {Function} options.onClose - called after socket closes
 * @param {number} options.backoffBaseMs - initial reconnect delay
 * @param {number} options.backoffMaxMs - max reconnect delay
 */
export function useWebSocket(
  url,
  onMessage,
  {
    onOpen = null,
    onClose = null,
    backoffBaseMs = 1000,
    backoffMaxMs = 10000,
  } = {}
) {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);
  const pendingMessagesRef = useRef([]);
  const shouldReconnectRef = useRef(false);
  const reconnectTimerRef = useRef(null);
  const lastUrlRef = useRef(url);
  const attemptRef = useRef(0);

  const connect = useCallback(
    (overrideUrl = null) => {
      const targetUrl = overrideUrl || lastUrlRef.current || url;
      lastUrlRef.current = targetUrl;

      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        return;
      }

      try {
        shouldReconnectRef.current = true;
        const ws = new WebSocket(targetUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          attemptRef.current = 0;
          console.log('WebSocket connected');
          setIsConnected(true);
          setError(null);

          if (typeof onOpen === 'function') {
            try {
              onOpen(ws);
            } catch (e) {
              console.error('WebSocket onOpen handler error:', e);
            }
          }

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

        ws.onclose = (evt) => {
          console.log('WebSocket closed', evt?.code, evt?.reason || '');
          setIsConnected(false);
          wsRef.current = null;

          if (typeof onClose === 'function') {
            try {
              onClose(evt);
            } catch (e) {
              console.error('WebSocket onClose handler error:', e);
            }
          }

          if (shouldReconnectRef.current) {
            const delay = Math.min(
              backoffMaxMs,
              backoffBaseMs * Math.pow(2, attemptRef.current)
            );
            attemptRef.current += 1;
            reconnectTimerRef.current = setTimeout(() => {
              connect(targetUrl);
            }, delay);
          }
        };
      } catch (e) {
        console.error('WebSocket connection failed:', e);
        setError('Failed to connect');
      }
    },
    [url, onMessage, onOpen, onClose, backoffBaseMs, backoffMaxMs]
  );

  const sendMessage = useCallback((message, options = {}) => {
    const { dropIfDisconnected = false, maxPending = 200 } = options;

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
    attemptRef.current = 0;
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

  const disableReconnect = useCallback(() => {
    shouldReconnectRef.current = false;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return { isConnected, error, connect, disconnect, disableReconnect, sendMessage };
}
