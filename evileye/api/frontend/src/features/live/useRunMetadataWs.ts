import { useEffect, useRef, useState } from 'react';
import { request, streamMetadataWsUrl, type StreamMetadata } from '../../api';

const REST_FALLBACK_MS = 1500;

function metadataFingerprint(payload: StreamMetadata): string {
  try {
    return JSON.stringify({
      objects: payload.objects ?? [],
      zones: payload.zones ?? [],
      signalization: payload.signalization ?? false,
    });
  } catch {
    return String(Date.now());
  }
}

async function parseWsPayload(data: unknown): Promise<string | null> {
  if (typeof data === 'string') return data;
  if (data instanceof Blob) {
    try {
      return await data.text();
    } catch {
      return null;
    }
  }
  return null;
}

export function useRunMetadataWs(rid: number | null, sourceId: number | null | undefined) {
  const [meta, setMeta] = useState<StreamMetadata | null>(null);
  const lastFingerprint = useRef<string>('');

  const applyMeta = (payload: StreamMetadata) => {
    const fp = metadataFingerprint(payload);
    if (fp === lastFingerprint.current) return;
    lastFingerprint.current = fp;
    setMeta(payload);
  };

  useEffect(() => {
    setMeta(null);
    lastFingerprint.current = '';
    if (rid == null) return;

    let cancelled = false;
    let ws: WebSocket | null = null;
    let retryTimer: number | null = null;
    let restTimer: number | null = null;
    let backoffMs = 1000;
    let wsOpen = false;

    const pollRest = async () => {
      if (cancelled || wsOpen) return;
      try {
        const qs = sourceId != null ? `?source_id=${sourceId}` : '';
        const payload = await request<StreamMetadata>(`/runs/${rid}/metadata${qs}`);
        if (!cancelled) applyMeta(payload);
      } catch {
        /* ignore */
      }
    };

    const startRestFallback = () => {
      if (restTimer != null) window.clearInterval(restTimer);
      void pollRest();
      restTimer = window.setInterval(() => void pollRest(), REST_FALLBACK_MS);
    };

    const stopRestFallback = () => {
      if (restTimer != null) {
        window.clearInterval(restTimer);
        restTimer = null;
      }
    };

    const connect = () => {
      if (cancelled) return;
      const url = streamMetadataWsUrl(rid, sourceId ?? null);
      try {
        ws = new WebSocket(url);
      } catch {
        startRestFallback();
        scheduleReconnect();
        return;
      }
      ws.onmessage = (ev) => {
        void (async () => {
          try {
            const raw = await parseWsPayload(ev.data);
            if (!raw) return;
            applyMeta(JSON.parse(raw) as StreamMetadata);
          } catch {
            /* ignore */
          }
        })();
      };
      ws.onopen = () => {
        backoffMs = 1000;
        wsOpen = true;
        stopRestFallback();
      };
      ws.onerror = () => {
        /* reconnect on close */
      };
      ws.onclose = () => {
        wsOpen = false;
        if (!cancelled) {
          startRestFallback();
          scheduleReconnect();
        }
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

    startRestFallback();
    connect();
    return () => {
      cancelled = true;
      wsOpen = false;
      if (retryTimer != null) window.clearTimeout(retryTimer);
      stopRestFallback();
      try {
        ws?.close();
      } catch {
        /* ignore */
      }
    };
  }, [rid, sourceId]);

  return meta;
}
