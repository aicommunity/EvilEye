/** Opt-in playback diagnostics for seek-while-play freezes. */

export type PlaybackDebugCounters = {
  seekCount: number;
  settleEnter: number;
  settleExit: number;
  settleActiveMs: number;
  seekPlaybackCalls: number;
  seekPlaybackSkippedSeeking: number;
  seekForceOverride: number;
  eofClampHits: number;
  pastEofHits: number;
  slotNullWipes: number;
  playCalls: number;
  playRejects: number;
  pauseFromScrub: number;
  clockEmits: number;
  clockOwnerSeekingMs: number;
  clockGraceDrops: number;
  rafTicks: number;
  rafSkippedScrub: number;
  rafSkippedFresh: number;
  rafAdvanced: number;
  watchdogKick: number;
  watchdogLoad: number;
  seekingStuckRecoveries: number;
};

export type PlaybackDebugSnapshotMeta = {
  playing?: boolean;
  scrubbing?: boolean;
  positionSec?: number;
  segmentsLen?: number;
  selectedIds?: string[];
  clockOwnerId?: string | null;
};

type PlaybackDebugApi = {
  enabled: boolean;
  counters: PlaybackDebugCounters;
  clockOwnerId: string | null;
  snapshot: () => Record<string, unknown>;
  reset: () => void;
  log: (event: string, extra?: Record<string, unknown>) => void;
  setMeta: (meta: PlaybackDebugSnapshotMeta) => void;
  setEnabled: (on: boolean) => void;
};

const COUNTER_KEYS: (keyof PlaybackDebugCounters)[] = [
  'seekCount',
  'settleEnter',
  'settleExit',
  'settleActiveMs',
  'seekPlaybackCalls',
  'seekPlaybackSkippedSeeking',
  'seekForceOverride',
  'eofClampHits',
  'pastEofHits',
  'slotNullWipes',
  'playCalls',
  'playRejects',
  'pauseFromScrub',
  'clockEmits',
  'clockOwnerSeekingMs',
  'clockGraceDrops',
  'rafTicks',
  'rafSkippedScrub',
  'rafSkippedFresh',
  'rafAdvanced',
  'watchdogKick',
  'watchdogLoad',
  'seekingStuckRecoveries',
];

function emptyCounters(): PlaybackDebugCounters {
  const c = {} as PlaybackDebugCounters;
  for (const k of COUNTER_KEYS) c[k] = 0;
  return c;
}

let enabled = false;
let counters = emptyCounters();
let meta: PlaybackDebugSnapshotMeta = {};
let settleEnteredAt = 0;
let periodicTimer: number | null = null;

function readStorageFlag(): boolean {
  try {
    return typeof localStorage !== 'undefined' && localStorage.getItem('playbackDebug') === '1';
  } catch {
    return false;
  }
}

function videoSnapshots() {
  if (typeof document === 'undefined') return [];
  return [...document.querySelectorAll('video')].map((v) => ({
    paused: v.paused,
    seeking: v.seeking,
    readyState: v.readyState,
    networkState: v.networkState,
    currentTime: v.currentTime,
    duration: Number.isFinite(v.duration) ? v.duration : null,
    error: v.error?.code ?? null,
  }));
}

function seekingStuckMs(): number {
  const videos = typeof document !== 'undefined' ? [...document.querySelectorAll('video')] : [];
  let max = 0;
  for (const v of videos) {
    if (!v.seeking) continue;
    // Age is tracked in playbackVideoSync WeakMap; approximate via readyState hang flag.
    max = Math.max(max, 1);
  }
  return max;
}

function buildSnapshot(): Record<string, unknown> {
  const videos = videoSnapshots();
  const seekingCount = videos.filter((v) => v.seeking).length;
  return {
    ...meta,
    clockOwnerId: meta.clockOwnerId ?? null,
    counters: { ...counters },
    videos,
    seekingCount,
    seekingStuckMs: seekingCount > 0 ? seekingStuckMs() : 0,
    clock: typeof document !== 'undefined'
      ? document.querySelector('.playback-position-clock')?.textContent ?? null
      : null,
  };
}

function ensurePeriodic() {
  if (!enabled || typeof window === 'undefined') return;
  if (periodicTimer != null) return;
  periodicTimer = window.setInterval(() => {
    if (!enabled) return;
    // eslint-disable-next-line no-console
    console.debug('[playback]', buildSnapshot());
  }, 1000);
}

function clearPeriodic() {
  if (periodicTimer == null || typeof window === 'undefined') return;
  window.clearInterval(periodicTimer);
  periodicTimer = null;
}

function publishApi(): void {
  if (typeof window === 'undefined') return;
  const api: PlaybackDebugApi = {
    get enabled() {
      return enabled;
    },
    get counters() {
      return counters;
    },
    get clockOwnerId() {
      return meta.clockOwnerId ?? null;
    },
    snapshot: buildSnapshot,
    reset: () => {
      counters = emptyCounters();
      meta = {};
      settleEnteredAt = 0;
    },
    log: (event, extra) => {
      if (!enabled) return;
      // eslint-disable-next-line no-console
      console.debug('[playback]', event, extra ?? '', buildSnapshot());
    },
    setMeta: (next) => {
      meta = { ...meta, ...next };
    },
    setEnabled: (on) => {
      enabled = on;
      if (on) {
        ensurePeriodic();
        publishApi();
      } else {
        clearPeriodic();
      }
    },
  };
  (window as Window & { __playbackDebug?: PlaybackDebugApi }).__playbackDebug = api;
}

export function isPlaybackDebugEnabled(): boolean {
  return enabled;
}

export function initPlaybackDebug(): void {
  if (typeof window === 'undefined') return;
  const win = window as Window & { __playbackDebug?: boolean | PlaybackDebugApi };
  if (win.__playbackDebug === true || readStorageFlag()) {
    enabled = true;
  }
  if (win.__playbackDebug === false) {
    enabled = false;
  }
  publishApi();
  if (enabled) ensurePeriodic();
}

export function playbackDebugInc(key: keyof PlaybackDebugCounters, by = 1): void {
  if (!enabled) return;
  counters[key] = (counters[key] ?? 0) + by;
}

export function playbackDebugLog(event: string, extra?: Record<string, unknown>): void {
  if (!enabled) return;
  // eslint-disable-next-line no-console
  console.debug('[playback]', event, extra ?? '');
}

export function playbackDebugSetMeta(next: PlaybackDebugSnapshotMeta): void {
  if (!enabled) return;
  meta = { ...meta, ...next };
}

export function playbackDebugMarkSettleEnter(): void {
  if (!enabled) return;
  playbackDebugInc('settleEnter');
  settleEnteredAt = performance.now();
  playbackDebugLog('settleEnter');
}

export function playbackDebugMarkSettleExit(): void {
  if (!enabled) return;
  playbackDebugInc('settleExit');
  if (settleEnteredAt > 0) {
    counters.settleActiveMs += Math.round(performance.now() - settleEnteredAt);
    settleEnteredAt = 0;
  }
  playbackDebugLog('settleExit');
}

// Boot once when the module loads in the browser.
if (typeof window !== 'undefined') {
  initPlaybackDebug();
}
