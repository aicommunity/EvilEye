/** Opt-in / force-enabled client diagnostics ring with optional server upload. */

import { playbackDebugSetEnabled } from '../features/playback/playbackDebug';

export type DiagPage = 'live' | 'playback' | 'auth' | 'other';

export type DiagEvent = {
  t: number;
  seq: number;
  kind: string;
  page: DiagPage;
  sessionId: string;
  user?: string;
  payload: Record<string, unknown>;
};

export type ClientTelemetryApi = {
  enabled: boolean;
  autoUpload: boolean;
  events: DiagEvent[];
  counters: Record<string, number>;
  snapshot: () => Record<string, unknown>;
  export: () => string;
  reset: () => void;
  setEnabled: (on: boolean, opts?: { autoUpload?: boolean }) => void;
  setUser: (user: string | null) => void;
  log: (kind: string, payload?: Record<string, unknown>, page?: DiagPage) => void;
};

const MAX_EVENTS = 500;
const FLUSH_MS = 5000;
const FLUSH_BATCH = 40;

let enabled = false;
let autoUpload = false;
let seq = 0;
let userName: string | null = null;
let events: DiagEvent[] = [];
const counters: Record<string, number> = {};
let flushTimer: number | null = null;
let pendingUpload: DiagEvent[] = [];
let sessionId = '';

function ensureSessionId(): string {
  if (sessionId) return sessionId;
  try {
    const existing = sessionStorage.getItem('evileye.diag.session');
    if (existing) {
      sessionId = existing;
      return sessionId;
    }
  } catch {
    /* ignore */
  }
  sessionId =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `s-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  try {
    sessionStorage.setItem('evileye.diag.session', sessionId);
  } catch {
    /* ignore */
  }
  return sessionId;
}

function readStorageFlag(): boolean {
  try {
    return typeof localStorage !== 'undefined' && localStorage.getItem('evileyeDebug') === '1';
  } catch {
    return false;
  }
}

function readQueryFlag(): boolean {
  try {
    return typeof location !== 'undefined' && new URLSearchParams(location.search).get('debug') === '1';
  } catch {
    return false;
  }
}

function bump(kind: string) {
  counters[kind] = (counters[kind] ?? 0) + 1;
}

function buildSnapshot(): Record<string, unknown> {
  return {
    enabled,
    autoUpload,
    user: userName,
    sessionId: ensureSessionId(),
    eventsLen: events.length,
    pendingUpload: pendingUpload.length,
    counters: { ...counters },
    recent: events.slice(-20),
  };
}

async function flushNow(): Promise<void> {
  if (!enabled || !autoUpload || !pendingUpload.length) return;
  if (typeof fetch === 'undefined') return;
  const batch = pendingUpload.splice(0, FLUSH_BATCH);
  try {
    await fetch('/api/v1/diagnostics/client', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: ensureSessionId(),
        user: userName,
        ua: typeof navigator !== 'undefined' ? navigator.userAgent.slice(0, 512) : undefined,
        page: batch[0]?.page,
        events: batch,
      }),
    });
  } catch {
    // Re-queue on failure (keep ring bound).
    pendingUpload = [...batch, ...pendingUpload].slice(0, MAX_EVENTS);
  }
  if (pendingUpload.length >= FLUSH_BATCH) {
    void flushNow();
  }
}

function ensureFlushTimer() {
  if (!enabled || !autoUpload || typeof window === 'undefined') return;
  if (flushTimer != null) return;
  flushTimer = window.setInterval(() => {
    void flushNow();
  }, FLUSH_MS);
}

function clearFlushTimer() {
  if (flushTimer == null || typeof window === 'undefined') return;
  window.clearInterval(flushTimer);
  flushTimer = null;
}

function publishApi(): void {
  if (typeof window === 'undefined') return;
  const api: ClientTelemetryApi = {
    get enabled() {
      return enabled;
    },
    get autoUpload() {
      return autoUpload;
    },
    get events() {
      return events;
    },
    get counters() {
      return counters;
    },
    snapshot: buildSnapshot,
    export: () => JSON.stringify(buildSnapshot(), null, 2),
    reset: () => {
      events = [];
      pendingUpload = [];
      for (const k of Object.keys(counters)) delete counters[k];
      seq = 0;
    },
    setEnabled: (on, opts) => {
      setClientTelemetryEnabled(on, opts);
    },
    setUser: (u) => {
      userName = u;
    },
    log: (kind, payload, page) => {
      clientTelemetryLog(kind, payload, page);
    },
  };
  (window as Window & { __evileyeDebug?: ClientTelemetryApi }).__evileyeDebug = api;
}

export function isClientTelemetryEnabled(): boolean {
  return enabled;
}

export function setClientTelemetryEnabled(on: boolean, opts?: { autoUpload?: boolean }): void {
  enabled = on;
  if (opts?.autoUpload != null) autoUpload = opts.autoUpload;
  else if (on && autoUpload === false && (readStorageFlag() || readQueryFlag())) autoUpload = true;
  try {
    playbackDebugSetEnabled(on);
  } catch {
    /* playbackDebug may not export setter yet during circular init */
  }
  if (on) ensureFlushTimer();
  else {
    clearFlushTimer();
    void flushNow();
  }
  publishApi();
}

export function setClientTelemetryUser(user: string | null): void {
  userName = user;
}

export function clientTelemetryLog(
  kind: string,
  payload: Record<string, unknown> = {},
  page: DiagPage = 'other',
): void {
  if (!enabled) return;
  bump(kind);
  const ev: DiagEvent = {
    t: Date.now(),
    seq: ++seq,
    kind,
    page,
    sessionId: ensureSessionId(),
    user: userName ?? undefined,
    payload,
  };
  events.push(ev);
  if (events.length > MAX_EVENTS) events = events.slice(-MAX_EVENTS);
  if (autoUpload) {
    pendingUpload.push(ev);
    if (pendingUpload.length >= FLUSH_BATCH) void flushNow();
  }
  // eslint-disable-next-line no-console
  if (typeof console !== 'undefined') console.debug('[evileyeDebug]', kind, payload);
}

export function applyClientDebugFromAuth(clientDebug: boolean | undefined, username?: string | null): void {
  if (username) setClientTelemetryUser(username);
  if (clientDebug) {
    setClientTelemetryEnabled(true, { autoUpload: true });
    clientTelemetryLog(
      'session_start',
      {
        user: username ?? null,
        force: true,
        ua: typeof navigator !== 'undefined' ? navigator.userAgent.slice(0, 256) : null,
        viewport:
          typeof window !== 'undefined'
            ? { w: window.innerWidth, h: window.innerHeight }
            : null,
        effectiveType:
          typeof navigator !== 'undefined'
            ? (navigator as Navigator & { connection?: { effectiveType?: string } }).connection
                ?.effectiveType ?? null
            : null,
      },
      'auth',
    );
  }
}

export function initClientTelemetry(): void {
  if (typeof window === 'undefined') return;
  ensureSessionId();
  const on = readStorageFlag() || readQueryFlag();
  if (on) setClientTelemetryEnabled(true, { autoUpload: true });
  else publishApi();
}

if (typeof window !== 'undefined') {
  initClientTelemetry();
}
