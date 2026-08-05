import { useCallback, useEffect, useRef, useState } from 'react';

export interface PreviewFrame {
  sourceId: number;
  blobUrl: string;
  etag: string;
  ts: number;
}

function liveGridWsUrl(runId: number): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/api/v1/runs/${runId}/ws/live`;
}

export function useLiveGridPreviewWs(runId: number | null, sourceIds: number[]) {
  const [frames, setFrames] = useState<Map<number, PreviewFrame>>(new Map());
  const [connected, setConnected] = useState(false);
  const [failed, setFailed] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const blobUrlsRef = useRef<Map<number, string>>(new Map());
  const pendingHeaderRef = useRef<{ source_id: number; etag?: string; ts?: number } | null>(null);
  const reconnectAttemptRef = useRef(0);

  const revokeBlob = useCallback((sourceId: number) => {
    const old = blobUrlsRef.current.get(sourceId);
    if (old) {
      URL.revokeObjectURL(old);
      blobUrlsRef.current.delete(sourceId);
    }
  }, []);

  const getBlobUrl = useCallback(
    (sourceId: number | null | undefined) => {
      if (sourceId == null) return undefined;
      return frames.get(sourceId)?.blobUrl;
    },
    [frames],
  );

  useEffect(() => {
    if (runId == null || !sourceIds.length) {
      setConnected(false);
      return;
    }

    let cancelled = false;
    let reconnectTimer: number | null = null;

    const connect = () => {
      if (cancelled) return;
      const ws = new WebSocket(liveGridWsUrl(runId));
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptRef.current = 0;
        setConnected(true);
        setFailed(false);
        ws.send(JSON.stringify({ op: 'subscribe', source_ids: sourceIds }));
      };

      ws.onmessage = async (ev) => {
        if (typeof ev.data === 'string') {
          try {
            const header = JSON.parse(ev.data) as { type?: string; source_id?: number; etag?: string; ts?: number };
            if (header.type === 'preview' && header.source_id != null) {
              pendingHeaderRef.current = {
                source_id: header.source_id,
                etag: header.etag,
                ts: typeof header.ts === 'number' ? header.ts : undefined,
              };
            }
          } catch {
            /* ignore */
          }
          return;
        }
        const header = pendingHeaderRef.current;
        pendingHeaderRef.current = null;
        if (!header) return;
        const blob = ev.data instanceof Blob ? ev.data : new Blob([ev.data]);
        const url = URL.createObjectURL(blob);
        revokeBlob(header.source_id);
        blobUrlsRef.current.set(header.source_id, url);
        setFrames((prev) => {
          const next = new Map(prev);
          next.set(header.source_id, {
            sourceId: header.source_id,
            blobUrl: url,
            etag: header.etag || '',
            ts: header.ts ?? Date.now() / 1000,
          });
          return next;
        });
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        if (!cancelled) {
          setFailed(true);
          const delay = Math.min(30000, 1000 * 2 ** reconnectAttemptRef.current);
          reconnectAttemptRef.current += 1;
          reconnectTimer = window.setTimeout(connect, delay);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer != null) window.clearTimeout(reconnectTimer);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      blobUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
      blobUrlsRef.current.clear();
      setFrames(new Map());
      setConnected(false);
    };
  }, [runId, sourceIds.join(','), revokeBlob]);

  return { frames, connected, failed, getBlobUrl };
}
