import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { streamSnapshotUrl } from '../../api';
import { clientTelemetryLog } from '../../diagnostics/clientTelemetry';

export interface PreviewFrame {
  runId: number;
  sourceId: number;
  blobUrl: string;
  etag: string;
  ts: number;
}

export type LivePreviewByRun = Map<number, number[]>;

export function frameKey(runId: number, sourceId: number): string {
  return `${runId}:${sourceId}`;
}

function liveGridWsUrl(runId: number): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/api/v1/runs/${runId}/ws/live`;
}

export async function fetchSnapshotBlob(
  runId: number,
  sourceId: number,
  etag?: string,
  signal?: AbortSignal,
): Promise<{ blob: Blob; etag: string } | null> {
  const url = streamSnapshotUrl(runId, sourceId);
  const headers: Record<string, string> = {};
  // A06: only precondition on an etag we already applied (never notify's fresh etag).
  if (etag) headers['If-None-Match'] = `"${etag}"`;
  const res = await fetch(url, { credentials: 'same-origin', headers, signal });
  if (res.status === 304) return null;
  if (!res.ok) return null;
  const blob = await res.blob();
  const nextEtag = (res.headers.get('etag') || etag || '').replace(/"/g, '');
  return { blob, etag: nextEtag };
}

function runsKey(byRun: LivePreviewByRun): string {
  return [...byRun.keys()].sort((a, b) => a - b).join(',');
}

function sourcesKey(byRun: LivePreviewByRun): string {
  const parts: string[] = [];
  for (const rid of [...byRun.keys()].sort((a, b) => a - b)) {
    const ids = [...(byRun.get(rid) ?? [])].sort((a, b) => a - b);
    parts.push(`${rid}:${ids.join(',')}`);
  }
  return parts.join('|');
}

type SocketState = {
  ws: WebSocket | null;
  pendingHeader: { source_id: number; etag?: string; ts?: number } | null;
  reconnectAttempt: number;
  reconnectTimer: number | null;
  pingTimer: number | null;
  cancelled: boolean;
};

/**
 * Live grid JPEG preview: one WS per run_id, frames keyed by (run_id, source_id).
 */
export function useLiveGridPreviewWs(byRun: LivePreviewByRun) {
  const [frames, setFrames] = useState<Map<string, PreviewFrame>>(new Map());
  const [connectedRuns, setConnectedRuns] = useState<Set<number>>(new Set());
  const [failed, setFailed] = useState(false);
  const blobUrlsRef = useRef<Map<string, string>>(new Map());
  const etagsRef = useRef<Map<string, string>>(new Map());
  const socketsRef = useRef<Map<number, SocketState>>(new Map());
  const byRunRef = useRef(byRun);
  byRunRef.current = byRun;
  const runIdsKey = useMemo(() => runsKey(byRun), [byRun]);
  const sourceIdsKey = useMemo(() => sourcesKey(byRun), [byRun]);

  const revokeBlob = useCallback((key: string) => {
    const old = blobUrlsRef.current.get(key);
    if (old) {
      URL.revokeObjectURL(old);
      blobUrlsRef.current.delete(key);
    }
    etagsRef.current.delete(key);
  }, []);

  const applyBlob = useCallback(
    (runId: number, sourceId: number, blob: Blob, etag: string, ts?: number) => {
      const key = frameKey(runId, sourceId);
      const url = URL.createObjectURL(blob);
      revokeBlob(key);
      blobUrlsRef.current.set(key, url);
      // Atomic: etag only when blob is applied (R10).
      if (etag) etagsRef.current.set(key, etag);
      setFrames((prev) => {
        const next = new Map(prev);
        next.set(key, {
          runId,
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
    (runId: number | null | undefined, sourceId: number | null | undefined) => {
      if (runId == null || sourceId == null) return undefined;
      return frames.get(frameKey(runId, sourceId))?.blobUrl;
    },
    [frames],
  );

  const getPreviewFrameAgeSec = useCallback(
    (runId: number | null | undefined, sourceId: number | null | undefined) => {
      if (runId == null || sourceId == null) return undefined;
      const frame = frames.get(frameKey(runId, sourceId));
      if (!frame?.ts) return undefined;
      return Math.max(0, Date.now() / 1000 - frame.ts);
    },
    [frames],
  );

  useEffect(() => {
    const sockets = socketsRef.current;

    const markConnected = (runId: number, on: boolean) => {
      setConnectedRuns((prev) => {
        const next = new Set(prev);
        if (on) next.add(runId);
        else next.delete(runId);
        return next;
      });
    };

    const wanted = new Set(
      runIdsKey
        .split(',')
        .filter(Boolean)
        .map((s) => Number(s))
        .filter((n) => Number.isFinite(n)),
    );

    // Close sockets for runs no longer needed (keep others alive — R10).
    for (const [rid, state] of [...sockets.entries()]) {
      if (wanted.has(rid)) continue;
      state.cancelled = true;
      if (state.reconnectTimer != null) window.clearTimeout(state.reconnectTimer);
      if (state.pingTimer != null) window.clearInterval(state.pingTimer);
      state.ws?.close();
      sockets.delete(rid);
      markConnected(rid, false);
    }

    const connectRun = (runId: number) => {
      if (sockets.has(runId)) return;
      const state: SocketState = {
        ws: null,
        pendingHeader: null,
        reconnectAttempt: 0,
        reconnectTimer: null,
        pingTimer: null,
        cancelled: false,
      };
      sockets.set(runId, state);
      let notifyGen = 0;
      let notifyAbort: AbortController | null = null;

      const connect = () => {
        if (state.cancelled || !sockets.has(runId)) return;
        const ws = new WebSocket(liveGridWsUrl(runId));
        ws.binaryType = 'arraybuffer';
        state.ws = ws;

        ws.onopen = () => {
          state.reconnectAttempt = 0;
          markConnected(runId, true);
          setFailed(false);
          const ids = byRunRef.current.get(runId) ?? [];
          clientTelemetryLog('ws_open', { runId, sourceIds: ids }, 'live');
          ws.send(JSON.stringify({ op: 'subscribe', source_ids: ids }));
          if (state.pingTimer != null) window.clearInterval(state.pingTimer);
          state.pingTimer = window.setInterval(() => {
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
              if (header.type === 'preview_notify' && header.source_id != null) {
                const sid = header.source_id;
                const key = frameKey(runId, sid);
                const prevEtag = etagsRef.current.get(key);
                notifyAbort?.abort();
                const ac = new AbortController();
                notifyAbort = ac;
                const gen = ++notifyGen;
                const fetched = await fetchSnapshotBlob(runId, sid, prevEtag, ac.signal);
                if (gen !== notifyGen || ac.signal.aborted || state.cancelled) return;
                if (fetched) applyBlob(runId, sid, fetched.blob, fetched.etag, header.ts);
                return;
              }
              if (header.type === 'preview' && header.source_id != null) {
                state.pendingHeader = {
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
          const header = state.pendingHeader;
          state.pendingHeader = null;
          if (!header) {
            clientTelemetryLog('ws_drop_no_header', { runId }, 'live');
            return;
          }
          const blob =
            ev.data instanceof Blob ? ev.data : new Blob([ev.data], { type: 'image/jpeg' });
          applyBlob(runId, header.source_id, blob, header.etag || '', header.ts);
        };

        ws.onclose = (ev) => {
          markConnected(runId, false);
          if (state.pingTimer != null) {
            window.clearInterval(state.pingTimer);
            state.pingTimer = null;
          }
          clientTelemetryLog(
            'ws_close',
            { runId, code: ev.code, reason: ev.reason || '', wasClean: ev.wasClean },
            'live',
          );
          if (!state.cancelled && sockets.has(runId)) {
            setFailed(true);
            const delay = Math.min(30000, 1000 * 2 ** state.reconnectAttempt);
            state.reconnectAttempt += 1;
            clientTelemetryLog(
              'ws_reconnect',
              { runId, attempt: state.reconnectAttempt, delayMs: delay },
              'live',
            );
            state.reconnectTimer = window.setTimeout(connect, delay);
          }
        };

        ws.onerror = () => {
          clientTelemetryLog('ws_error', { runId }, 'live');
          ws.close();
        };
      };

      connect();
    };

    for (const runId of wanted) {
      connectRun(runId);
    }
  }, [runIdsKey, applyBlob]);

  // Unmount only: tear down all sockets and blobs (R10).
  useEffect(() => {
    return () => {
      const sockets = socketsRef.current;
      for (const [, state] of sockets) {
        state.cancelled = true;
        if (state.reconnectTimer != null) window.clearTimeout(state.reconnectTimer);
        if (state.pingTimer != null) window.clearInterval(state.pingTimer);
        state.ws?.close();
      }
      sockets.clear();
      blobUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
      blobUrlsRef.current.clear();
      etagsRef.current.clear();
      setFrames(new Map());
      setConnectedRuns(new Set());
    };
  }, []);

  useEffect(() => {
    for (const [runId, state] of socketsRef.current) {
      const ws = state.ws;
      if (!ws || ws.readyState !== WebSocket.OPEN) continue;
      const ids = byRunRef.current.get(runId) ?? [];
      clientTelemetryLog('ws_resubscribe', { runId, sourceIds: ids }, 'live');
      ws.send(JSON.stringify({ op: 'subscribe', source_ids: ids }));
    }
  }, [sourceIdsKey]);

  return {
    frames,
    connected: connectedRuns.size > 0,
    failed,
    getBlobUrl,
    getPreviewFrameAgeSec,
  };
}
