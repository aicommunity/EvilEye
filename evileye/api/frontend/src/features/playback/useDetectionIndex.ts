import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, cacheGet, cacheSet, isAbortError, playbackApi, type PlaybackDetectionItem } from '../../api';
import { mergeGlobalDetectionTs } from './detectionSync';

const DETECTIONS_CACHE_TTL_MS = 90_000;
const BACKOFF_MS = [5_000, 10_000, 20_000, 30_000];

function detectionsCacheKey(
  date: string,
  runId: number | null,
  fromSec: number,
  toSec: number,
  cameras: string[],
): string {
  return `playback:detections:${date}:${runId ?? 'none'}:${Math.round(fromSec)}:${Math.round(toSec)}:ticks-preview-v2:${cameras.join(',')}`;
}

/** Merge detection tick rows per camera (ts/kind/object_id). */
export function mergeDetectionItems(
  prev: Record<string, PlaybackDetectionItem[]>,
  incoming: Record<string, PlaybackDetectionItem[]>,
  cameras: string[],
): Record<string, PlaybackDetectionItem[]> {
  const merged: Record<string, PlaybackDetectionItem[]> = {};
  for (const cam of cameras) {
    const byKey = new Map<string, PlaybackDetectionItem>();
    for (const it of [...(prev[cam] ?? []), ...(incoming[cam] ?? [])]) {
      if (!Number.isFinite(it.ts)) continue;
      const key = `${it.ts}:${it.kind}:${it.object_id ?? 'anon'}`;
      if (!byKey.has(key)) byKey.set(key, it);
    }
    merged[cam] = Array.from(byKey.values()).sort((a, b) => a.ts - b.ts);
  }
  return merged;
}

function isBusyOrTimeout(e: unknown): boolean {
  if (!(e instanceof ApiError)) return false;
  if (e.status !== 503) return false;
  const detail = String(e.message || '').toLowerCase();
  return detail.includes('busy') || detail.includes('timeout') || detail.includes('detections');
}

async function fetchDetectionTicks(
  cameras: string[],
  opts: {
    date: string;
    runId: number | null;
    fromSec: number;
    toSec: number;
    signal?: AbortSignal;
  },
): Promise<Record<string, PlaybackDetectionItem[]>> {
  const cacheKey = detectionsCacheKey(opts.date, opts.runId, opts.fromSec, opts.toSec, cameras);
  const cached = cacheGet<{ by_camera: Record<string, PlaybackDetectionItem[]> }>(cacheKey);
  if (cached?.by_camera) {
    return cached.by_camera;
  }

  const res = await playbackApi.detections(cameras, {
    date: opts.date,
    runId: opts.runId,
    from: opts.fromSec,
    to: opts.toSec,
    ticksOnly: true,
    signal: opts.signal,
  });
  cacheSet(cacheKey, { by_camera: res.by_camera ?? {} }, DETECTIONS_CACHE_TTL_MS);

  const mapped: Record<string, PlaybackDetectionItem[]> = {};
  for (const cam of cameras) {
    mapped[cam] = res.by_camera?.[cam] ?? [];
  }
  return mapped;
}

/**
 * Archive detection index: ticks with optional preview_path / bounding_box for gap static frames.
 */
export function useDetectionIndex({
  cameras,
  date,
  runId,
  priorityFromSec,
  priorityToSec,
  backgroundFromSec,
  backgroundToSec,
  enabled,
}: {
  cameras: string[];
  date: string;
  runId: number | null;
  priorityFromSec: number | null;
  priorityToSec: number | null;
  backgroundFromSec: number | null;
  backgroundToSec: number | null;
  enabled: boolean;
}) {
  const [tickByCamera, setTickByCamera] = useState<Record<string, PlaybackDetectionItem[]>>({});
  const [loading, setLoading] = useState(false);
  const backoffStepRef = useRef(0);
  const backoffUntilRef = useRef(0);

  const cameraKey = cameras.join(',');
  const queryKey = `${date}:${runId ?? 'none'}:${cameraKey}`;

  // Prefer day-wide ticks; fall back to viewport window if day bounds missing.
  const ticksFromSec = backgroundFromSec ?? priorityFromSec;
  const ticksToSec = backgroundToSec ?? priorityToSec;
  const dayWideTicks =
    backgroundFromSec != null &&
    backgroundToSec != null &&
    (priorityFromSec == null ||
      priorityToSec == null ||
      (backgroundFromSec <= priorityFromSec && backgroundToSec >= priorityToSec));

  useEffect(() => {
    if (!enabled || !cameras.length) {
      setTickByCamera({});
      setLoading(false);
      return;
    }
    setTickByCamera({});
    backoffStepRef.current = 0;
    backoffUntilRef.current = 0;
  }, [enabled, queryKey]);

  useEffect(() => {
    if (!enabled || !cameras.length || ticksFromSec == null || ticksToSec == null) {
      setTickByCamera({});
      setLoading(false);
      return;
    }

    const fromSec = Math.floor(ticksFromSec);
    const toSec = Math.ceil(ticksToSec);
    const ac = new AbortController();
    let retryTimer: number | null = null;

    const run = () => {
      if (ac.signal.aborted) return;
      const now = Date.now();
      if (now < backoffUntilRef.current) {
        retryTimer = window.setTimeout(run, backoffUntilRef.current - now);
        return;
      }
      setLoading(true);
      void fetchDetectionTicks(cameras, {
        date,
        runId,
        fromSec,
        toSec,
        signal: ac.signal,
      })
        .then((mapped) => {
          if (ac.signal.aborted) return;
          backoffStepRef.current = 0;
          setTickByCamera((prev) => mergeDetectionItems(prev, mapped, cameras));
        })
        .catch((e) => {
          if (isAbortError(e) || ac.signal.aborted) return;
          if (isBusyOrTimeout(e)) {
            const step = backoffStepRef.current;
            const delay = BACKOFF_MS[Math.min(step, BACKOFF_MS.length - 1)];
            backoffStepRef.current = Math.min(step + 1, BACKOFF_MS.length - 1);
            backoffUntilRef.current = Date.now() + delay;
            retryTimer = window.setTimeout(run, delay);
            return;
          }
          setTickByCamera({});
        })
        .finally(() => {
          if (!ac.signal.aborted) setLoading(false);
        });
    };

    run();

    return () => {
      ac.abort();
      if (retryTimer != null) window.clearTimeout(retryTimer);
    };
  }, [
    cameraKey,
    date,
    runId,
    ticksFromSec == null ? null : Math.floor(ticksFromSec),
    ticksToSec == null ? null : Math.ceil(ticksToSec),
    enabled,
  ]);

  // If primary window was viewport-only, still pull day ticks once for full-timeline markers.
  useEffect(() => {
    if (
      !enabled ||
      !cameras.length ||
      backgroundFromSec == null ||
      backgroundToSec == null ||
      dayWideTicks ||
      loading
    ) {
      return;
    }

    const ac = new AbortController();
    let retryTimer: number | null = null;

    const run = () => {
      if (ac.signal.aborted) return;
      const now = Date.now();
      if (now < backoffUntilRef.current) {
        retryTimer = window.setTimeout(run, backoffUntilRef.current - now);
        return;
      }
      void fetchDetectionTicks(cameras, {
        date,
        runId,
        fromSec: backgroundFromSec,
        toSec: backgroundToSec,
        signal: ac.signal,
      })
        .then((mapped) => {
          if (ac.signal.aborted) return;
          setTickByCamera((prev) => mergeDetectionItems(prev, mapped, cameras));
        })
        .catch((e) => {
          if (isAbortError(e) || ac.signal.aborted) return;
          if (isBusyOrTimeout(e)) {
            const step = backoffStepRef.current;
            const delay = BACKOFF_MS[Math.min(step, BACKOFF_MS.length - 1)];
            backoffStepRef.current = Math.min(step + 1, BACKOFF_MS.length - 1);
            backoffUntilRef.current = Date.now() + delay;
            retryTimer = window.setTimeout(run, delay);
          }
        });
    };

    run();

    return () => {
      ac.abort();
      if (retryTimer != null) window.clearTimeout(retryTimer);
    };
  }, [
    cameraKey,
    date,
    runId,
    backgroundFromSec,
    backgroundToSec,
    enabled,
    dayWideTicks,
    loading,
  ]);

  const seedTicks = useCallback(
    (incoming: Record<string, PlaybackDetectionItem[]>) => {
      if (!enabled || !cameras.length) return;
      setTickByCamera((prev) => mergeDetectionItems(prev, incoming, cameras));
    },
    [enabled, cameras, cameraKey],
  );

  const byCamera = tickByCamera;
  const globalTs = useMemo(() => mergeGlobalDetectionTs(byCamera), [byCamera]);
  const hasDetections = globalTs.length > 0;

  return {
    byCamera,
    globalTs,
    hasDetections,
    loading,
    backgroundLoading: false,
    seedTicks,
  };
}
