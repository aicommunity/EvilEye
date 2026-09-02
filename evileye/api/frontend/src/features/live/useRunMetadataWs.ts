import { useEffect, useState } from 'react';
import { request, streamMetadataWsUrl, type StreamMetadata } from '../../api';

const REST_FALLBACK_MS = 1500;
export const METADATA_TTL_MS = 4000;

function metadataFingerprint(payload: StreamMetadata): string {
  try {
    return JSON.stringify({
      objects: payload.objects ?? [],
      zones: payload.zones ?? [],
      signalization: payload.signalization ?? false,
      event_labels: payload.event_labels ?? [],
      event_color: payload.event_color ?? null,
      debug_rois: payload.debug_rois ?? [],
      overlay: payload.overlay ?? null,
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

type SourceKey = number | null;
type Subscriber = (payload: StreamMetadata) => void;
type FreshnessSubscriber = (fresh: boolean) => void;

class RunMetadataStore {
  readonly rid: number;
  private ws: WebSocket | null = null;
  private wsOpen = false;
  private cancelled = false;
  private backoffMs = 1000;
  private retryTimer: number | null = null;
  private restTimer: number | null = null;

  private listenersBySource: Map<SourceKey, Set<Subscriber>> = new Map();
  private freshnessListenersBySource: Map<SourceKey, Set<FreshnessSubscriber>> = new Map();
  private latestBySource: Map<SourceKey, StreamMetadata> = new Map();
  private latestAtBySource: Map<SourceKey, number> = new Map();
  private fpBySource: Map<SourceKey, string> = new Map();
  private freshnessTimer: number | null = null;

  constructor(rid: number) {
    this.rid = rid;
  }

  subscribe(sourceId: SourceKey, cb: Subscriber): () => void {
    if (this.cancelled) this.cancelled = false;
    if (!this.listenersBySource.has(sourceId)) this.listenersBySource.set(sourceId, new Set());
    this.listenersBySource.get(sourceId)!.add(cb);
    const latest = this.latestBySource.get(sourceId);
    if (latest) cb(latest);
    // Lazily connect: first subscriber triggers connect.
    if (!this.ws) void this.connect();
    this._ensureFreshnessTimer();
    return () => {
      this.listenersBySource.get(sourceId)?.delete(cb);
      // Stop only when the last subscriber for all source keys is removed.
      if ([...this.listenersBySource.values()].every((s) => s.size === 0)) {
        this.close();
      }
    };
  }

  subscribeFreshness(sourceId: SourceKey, cb: FreshnessSubscriber): () => void {
    if (!this.freshnessListenersBySource.has(sourceId)) {
      this.freshnessListenersBySource.set(sourceId, new Set());
    }
    this.freshnessListenersBySource.get(sourceId)!.add(cb);
    cb(this.isFresh(sourceId));
    this._ensureFreshnessTimer();
    return () => {
      this.freshnessListenersBySource.get(sourceId)?.delete(cb);
      if ([...this.freshnessListenersBySource.values()].every((s) => s.size === 0)) {
        this._stopFreshnessTimer();
      }
    };
  }

  isFresh(sourceId: SourceKey, ttlMs = METADATA_TTL_MS): boolean {
    const at = this.latestAtBySource.get(sourceId);
    return at != null && Date.now() - at < ttlMs;
  }

  private _ensureFreshnessTimer() {
    if (this.freshnessTimer != null) return;
    this.freshnessTimer = window.setInterval(() => this._notifyFreshness(), 500);
  }

  private _stopFreshnessTimer() {
    if (this.freshnessTimer != null) {
      window.clearInterval(this.freshnessTimer);
      this.freshnessTimer = null;
    }
  }

  private _notifyFreshness() {
    const keys = new Set<SourceKey>([
      ...this.freshnessListenersBySource.keys(),
      ...this.latestAtBySource.keys(),
    ]);
    for (const key of keys) {
      const subs = this.freshnessListenersBySource.get(key);
      if (!subs?.size) continue;
      const fresh = this.isFresh(key);
      subs.forEach((fn) => fn(fresh));
    }
  }

  private pushPayload(payload: StreamMetadata) {
    if (this.cancelled) return;
    const key: SourceKey = payload.source_id ?? null;
    this.latestAtBySource.set(key, Date.now());
    this._notifyFreshness();
    const fp = metadataFingerprint(payload);
    const lastFp = this.fpBySource.get(key);
    if (fp === lastFp) return;
    this.fpBySource.set(key, fp);
    this.latestBySource.set(key, payload);

    const subs = this.listenersBySource.get(key);
    if (!subs?.size) return;
    subs.forEach((fn) => fn(payload));
  }

  private startRestFallback() {
    if (this.restTimer != null) window.clearInterval(this.restTimer);
    const pollRest = async () => {
      if (this.cancelled || this.wsOpen) return;
      const sourceKeys = [...this.listenersBySource.entries()]
        .filter(([, subs]) => subs.size > 0)
        .map(([sourceId]) => sourceId);
      if (!sourceKeys.length) return;

      for (const sourceId of sourceKeys) {
        try {
          const qs = sourceId != null ? `?source_id=${sourceId}` : '';
          const payload = await request<StreamMetadata>(`/runs/${this.rid}/metadata${qs}`);
          if (!this.cancelled) this.pushPayload(payload);
        } catch {
          /* ignore */
        }
      }
    };
    void pollRest();
    this.restTimer = window.setInterval(() => void pollRest(), REST_FALLBACK_MS);
  }

  private stopRestFallback() {
    if (this.restTimer != null) {
      window.clearInterval(this.restTimer);
      this.restTimer = null;
    }
  }

  private scheduleReconnect() {
    if (this.cancelled) return;
    if (this.retryTimer != null) window.clearTimeout(this.retryTimer);
    this.retryTimer = window.setTimeout(() => {
      this.backoffMs = Math.min(this.backoffMs * 2, 8000);
      void this.connect();
    }, this.backoffMs);
  }

  private async connect() {
    if (this.cancelled) return;
    if (this.wsOpen) return;
    if (this.ws != null && this.ws.readyState === WebSocket.OPEN) return;

    // If a previous attempt failed quickly, keep backoff in effect.
    const url = streamMetadataWsUrl(this.rid, null);
    try {
      this.ws = new WebSocket(url);
    } catch {
      this.startRestFallback();
      this.scheduleReconnect();
      return;
    }

    this.wsOpen = false;

    this.ws.onmessage = (ev) => {
      void (async () => {
        try {
          const raw = await parseWsPayload(ev.data);
          if (!raw) return;
          this.pushPayload(JSON.parse(raw) as StreamMetadata);
        } catch {
          /* ignore */
        }
      })();
    };

    this.ws.onopen = () => {
      this.backoffMs = 1000;
      this.wsOpen = true;
      this.stopRestFallback();
    };

    this.ws.onerror = () => {
      /* reconnect on close */
    };

    this.ws.onclose = () => {
      this.wsOpen = false;
      if (!this.cancelled) {
        this.startRestFallback();
        this.scheduleReconnect();
      }
    };
  }

  private close() {
    this.cancelled = true;
    this._stopFreshnessTimer();
    if (this.retryTimer != null) window.clearTimeout(this.retryTimer);
    if (this.restTimer != null) window.clearInterval(this.restTimer);
    this.retryTimer = null;
    this.restTimer = null;
    try {
      this.ws?.close();
    } catch {
      /* ignore */
    }
    this.ws = null;
  }
}

const runStores = new Map<number, RunMetadataStore>();
function getRunStore(rid: number) {
  let store = runStores.get(rid);
  if (!store) {
    store = new RunMetadataStore(rid);
    runStores.set(rid, store);
  }
  return store;
}

export function useRunMetadataWs(rid: number | null, sourceId: number | null | undefined) {
  const [meta, setMeta] = useState<StreamMetadata | null>(null);
  useEffect(() => {
    setMeta(null);
    if (rid == null) return;

    const key: SourceKey = sourceId ?? null;
    const store = getRunStore(rid);
    const unsub = store.subscribe(key, (payload) => setMeta(payload));
    return () => {
      unsub();
    };
  }, [rid, sourceId]);

  return meta;
}

export function useMetadataFreshness(
  rid: number | null,
  sourceId: number | null | undefined,
  ttlMs = METADATA_TTL_MS,
) {
  const [fresh, setFresh] = useState(false);
  useEffect(() => {
    setFresh(false);
    if (rid == null) return;
    const key: SourceKey = sourceId ?? null;
    const store = getRunStore(rid);
    const unsub = store.subscribeFreshness(key, (isFresh) => setFresh(isFresh));
    const timer = window.setInterval(() => setFresh(store.isFresh(key, ttlMs)), 500);
    return () => {
      unsub();
      window.clearInterval(timer);
    };
  }, [rid, sourceId, ttlMs]);
  return fresh;
}
