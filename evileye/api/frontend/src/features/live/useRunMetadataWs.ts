import { useEffect, useRef, useState } from 'react';
import { streamMetadataWsUrl, type StreamMetadata } from '../../api';

export function useRunMetadataWs(rid: number | null, sourceId: number | null | undefined) {
  const [meta, setMeta] = useState<StreamMetadata | null>(null);
  const lastFp = useRef<string>('');

  useEffect(() => {
    setMeta(null);
    lastFp.current = '';
    if (rid == null) return;

    let cancelled = false;
    let ws: WebSocket | null = null;
    let retryTimer: number | null = null;
    let backoffMs = 1000;

    const connect = () => {
      if (cancelled) return;
      const url = streamMetadataWsUrl(rid, sourceId ?? null);
      try {
        ws = new WebSocket(url);
      } catch {
        scheduleReconnect();
        return;
      }
      ws.onmessage = (ev) => {
        try {
          const raw = String(ev.data);
          if (raw === lastFp.current) return;
          lastFp.current = raw;
          setMeta(JSON.parse(raw) as StreamMetadata);
        } catch {
          /* ignore */
        }
      };
      ws.onopen = () => {
        backoffMs = 1000;
      };
      ws.onerror = () => {
        /* reconnect on close */
      };
      ws.onclose = () => {
        if (!cancelled) scheduleReconnect();
      };
    };

    const scheduleReconnect = () => {
      if (cancelled) return;
      if (retryTimer != null) window.clearTimeout(retryTimer);
      retryTimer = window.setTimeout(() => {
        backoffMs = Math.min(backoffMs * 2, 8000);
        connect();
      }, backoffMs);
    };

    connect();
    return () => {
      cancelled = true;
      if (retryTimer != null) window.clearTimeout(retryTimer);
      try {
        ws?.close();
      } catch {
        /* ignore */
      }
    };
  }, [rid, sourceId]);

  return meta;
}
