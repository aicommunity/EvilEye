import { useCallback, useEffect, useRef, useState } from 'react';
import { streamSnapshotUrl } from '../../api';

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

async function fetchSnapshotBlob(
  runId: number,
  sourceId: number,
  etag?: string,
): Promise<{ blob: Blob; etag: string } | null> {
  const url = streamSnapshotUrl(runId, sourceId);
  const headers: Record<string, string> = {};
  if (etag) headers['If-None-Match'] = `"${etag}"`;
  const res = await fetch(url, { credentials: 'same-origin', headers });
  if (res.status === 304) return null;
  if (!res.ok) return null;
  const blob = await res.blob();
  const nextEtag = (res.headers.get('etag') || etag || '').replace(/"/g, '');
  return { blob, etag: nextEtag };
}

export function useLiveGridPreviewWs(runId: number | null, sourceIds: number[]) {
  const [frames, setFrames] = useState<Map<number, PreviewFrame>>(new Map());
  const [connected, setConnected] = useState(false);
  const [failed, setFailed] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const blobUrlsRef = useRef<Map<number, string>>(new Map());
  const pendingHeaderRef = useRef<{ source_id: number; etag?: string; ts?: number } | null>(null);
  const etagsRef = useRef<Map<number, string>>(new Map());
  const reconnectAttemptRef = useRef(0);

  const revokeBlob = useCallback((sourceId: number) => {
    const old = blobUrlsRef.current.get(sourceId);
    if (old) {
      URL.revokeObjectURL(old);
      blobUrlsRef.current.delete(sourceId);
    }
  }, []);

  const applyBlob = useCallback(
    (sourceId: number, blob: Blob, etag: string, ts?: number) => {
      const url = URL.createObjectURL(blob);
      revokeBlob(sourceId);
      blobUrlsRef.current.set(sourceId, url);
      if (etag) etagsRef.current.set(sourceId, etag);
      setFrames((prev) => {
        const next = new Map(prev);
        next.set(sourceId, {
          sourceId,
          blobUrl: url,
          etag: etag || '',
          ts: ts ?? Date.now() / 1000,
        });
        return next;
      });
    },
    [revokeBlob],
  );

  const getBlobUrl = useCallback(
    (sourceId: number | null | undefined) => {
      if (sourceId == null) return undefined;
      return frames.get(sourceId)?.blobUrl;
    },
    [frames],
  );

  const getPreviewFrameAgeSec = useCallback(
    (sourceId: number | null | undefined) => {
      if (sourceId == null) return undefined;
      const frame = frames.get(sourceId);
      if (!frame?.ts) return undefined;
      return Math.max(0, Date.now() / 1000 - frame.ts);
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
    let pingTimer: number | null = null;

    const connect = () => {
      if (cancelled) return;
      const ws = new WebSocket(liveGridWsUrl(runId));
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptRef.current = 0;
        setConnected(true);
        setFailed(false);
        ws.send(JSON.stringify({ op: 'subscribe', source_ids: sourceIds }));
        if (pingTimer != null) window.clearInterval(pingTimer);
        pingTimer = window.setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ op: 'ping' }));
          }
        }, 5000);
      };

      ws.onmessage = async (ev) => {
        if (typeof ev.data === 'string') {
          try {
            const header = JSON.parse(ev.data) as {
              type?: string;
              source_id?: number;
              etag?: string;
              ts?: number;
              op?: string;
            };
            if (header.op === 'pong') return;
            if (header.type === 'preview_notify' && header.source_id != null && runId != null) {
              const sid = header.source_id;
              const prevEtag = header.etag || etagsRef.current.get(sid);
              const fetched = await fetchSnapshotBlob(runId, sid, prevEtag);
              if (fetched) applyBlob(sid, fetched.blob, fetched.etag, header.ts);
              return;
            }
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
        const blob =
          ev.data instanceof Blob
            ? ev.data
            : new Blob([ev.data], { type: 'image/jpeg' });
        applyBlob(header.source_id, blob, header.etag || '', header.ts);
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        if (pingTimer != null) {
          window.clearInterval(pingTimer);
          pingTimer = null;
        }
        // Keep last blob URLs until unmount or a newer frame arrives (avoid empty flash).
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
      if (pingTimer != null) window.clearInterval(pingTimer);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      blobUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
      blobUrlsRef.current.clear();
      setFrames(new Map());
      setConnected(false);
    };
  }, [runId, sourceIds.join(','), applyBlob]);

  return { frames, connected, failed, getBlobUrl, getPreviewFrameAgeSec };
}
