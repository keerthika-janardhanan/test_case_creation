import { useEffect, useMemo, useRef, useState } from "react";

import { buildWebSocketUrl } from "../api/client";

export interface RecorderEvent {
  message?: string;
  level?: string;
  [key: string]: unknown;
}

export function useRecorderStream(sessionId: string | null) {
  const [events, setEvents] = useState<RecorderEvent[]>([]);
  const [status, setStatus] = useState<"idle" | "connecting" | "open" | "closed">(
    "idle",
  );
  const wsRef = useRef<WebSocket | null>(null);

  const url = useMemo(() => {
    if (!sessionId) {
      return null;
    }
    const encoded = encodeURIComponent(sessionId);
    return buildWebSocketUrl(`/ws/recorder/${encoded}`);
  }, [sessionId]);

  useEffect(() => {
    if (!url) {
      setEvents([]);
      setStatus("idle");
      return;
    }

    setStatus("connecting");
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setStatus("open");
    ws.onclose = () => setStatus("closed");
    ws.onerror = () => setStatus("closed");
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as RecorderEvent;
        setEvents((prev) => [...prev, payload]);
      } catch {
        setEvents((prev) => [...prev, { message: event.data, level: "info" }]);
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [url]);

  return { events, status };
}

