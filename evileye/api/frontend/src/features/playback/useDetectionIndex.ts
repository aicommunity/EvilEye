import { useEffect, useMemo, useState } from 'react';
import { cacheGet, cacheSet, isAbortError, playbackApi, type PlaybackDetectionItem } from '../../api';
import { mergeGlobalDetectionTs } from './detectionSync';

const DETECTIONS_CACHE_TTL_MS = 90_000;

function detectionsCacheKey(
  date: string,
  runId: number | null,
  fromSec: number,
  toSec: number,
  cameras: string[],
  ticksOnly: boolean,
): string {
  return `playback:detections:${date}:${runId ?? 'none'}:${Math.round(fromSec)}:${Math.round(toSec)}:${ticksOnly ? 'ticks' : 'full'}:${cameras.join(',')}`;
}

function mergeDetectionItems(
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
      const existing = byKey.get(key);
      if (!existing) {
        byKey.set(key, it);
        continue;
      }
      if (!existing.bounding_box && it.bounding_box) {
        byKey.set(key, it);
      }
    }
    merged[cam] = Array.from(byKey.values()).sort((a, b) => a.ts - b.ts);
  }
  return merged;
}

async function fetchDetections(
  cameras: string[],
  opts: {
    date: string;
    runId: number | null;
    fromSec: number;
    toSec: number;
    ticksOnly?: boolean;
    signal?: AbortSignal;
  },
): Promise<Record<string, PlaybackDetectionItem[]>> {
  const cacheKey = detectionsCacheKey(
    opts.date,
    opts.runId,
    opts.fromSec,
    opts.toSec,
    cameras,
    Boolean(opts.ticksOnly),
  );
  const cached = cacheGet<{ by_camera: Record<string, PlaybackDetectionItem[]> }>(cacheKey);
  if (cached?.by_camera) {
    return cached.by_camera;
  }

  const res = await playbackApi.detections(cameras, {
    date: opts.date,
    runId: opts.runId,
    from: opts.fromSec,
    to: opts.toSec,
    ticksOnly: opts.ticksOnly,
    signal: opts.signal,
  });
  cacheSet(cacheKey, { by_camera: res.by_camera ?? {} }, DETECTIONS_CACHE_TTL_MS);

  const mapped: Record<string, PlaybackDetectionItem[]> = {};
  for (const cam of cameras) {
    mapped[cam] = res.by_camera?.[cam] ?? [];
  }
  return mapped;
}

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
  const [fullByCamera, setFullByCamera] = useState<Record<string, PlaybackDetectionItem[]>>({});
  const [tickByCamera, setTickByCamera] = useState<Record<string, PlaybackDetectionItem[]>>({});
  const [priorityLoading, setPriorityLoading] = useState(false);
  const [backgroundLoading, setBackgroundLoading] = useState(false);

  const cameraKey = cameras.join(',');
  const queryKey = `${date}:${runId ?? 'none'}:${cameraKey}`;

  useEffect(() => {
    if (!enabled || !cameras.length) {
      setFullByCamera({});
      setTickByCamera({});
      setPriorityLoading(false);
      setBackgroundLoading(false);
      return;
    }
    setFullByCamera({});
    setTickByCamera({});
  }, [enabled, queryKey]);

  useEffect(() => {
    if (!enabled || !cameras.length || priorityFromSec == null || priorityToSec == null) {
      setFullByCamera({});
      setPriorityLoading(false);
      return;
    }

    const ac = new AbortController();
    setPriorityLoading(true);

    void fetchDetections(cameras, {
      date,
      runId,
      fromSec: priorityFromSec,
      toSec: priorityToSec,
      ticksOnly: false,
      signal: ac.signal,
    })
      .then((mapped) => {
        if (ac.signal.aborted) return;
        setFullByCamera((prev) => mergeDetectionItems(prev, mapped, cameras));
      })
      .catch((e) => {
        if (isAbortError(e) || ac.signal.aborted) return;
        setFullByCamera({});
      })
      .finally(() => {
        if (!ac.signal.aborted) setPriorityLoading(false);
      });

    return () => ac.abort();
  }, [cameraKey, date, runId, priorityFromSec, priorityToSec, enabled]);

  useEffect(() => {
    if (
      !enabled ||
      !cameras.length ||
      backgroundFromSec == null ||
      backgroundToSec == null ||
      priorityFromSec == null ||
      priorityToSec == null
    ) {
      setBackgroundLoading(false);
      return;
    }

    if (backgroundFromSec >= priorityFromSec && backgroundToSec <= priorityToSec) {
      setBackgroundLoading(false);
      return;
    }

    const ac = new AbortController();
    setBackgroundLoading(true);

    void fetchDetections(cameras, {
      date,
      runId,
      fromSec: backgroundFromSec,
      toSec: backgroundToSec,
      ticksOnly: true,
      signal: ac.signal,
    })
      .then((mapped) => {
        if (ac.signal.aborted) return;
        setTickByCamera((prev) => mergeDetectionItems(prev, mapped, cameras));
      })
      .catch((e) => {
        if (isAbortError(e) || ac.signal.aborted) return;
      })
      .finally(() => {
        if (!ac.signal.aborted) setBackgroundLoading(false);
      });

    return () => ac.abort();
  }, [
    cameraKey,
    date,
    runId,
    backgroundFromSec,
    backgroundToSec,
    priorityFromSec,
    priorityToSec,
    enabled,
  ]);

  const byCamera = useMemo(() => fullByCamera, [fullByCamera]);
  const globalTs = useMemo(
    () => mergeGlobalDetectionTs(mergeDetectionItems(tickByCamera, fullByCamera, cameras)),
    [tickByCamera, fullByCamera, cameras],
  );
  const hasDetections = globalTs.length > 0;

  return {
    byCamera,
    globalTs,
    hasDetections,
    loading: priorityLoading,
    backgroundLoading,
  };
}
