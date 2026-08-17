import { useEffect, useRef, useState } from 'react';
import { isAbortError, playbackApi, type StreamMetadata } from '../../api';
import { localDateString } from './timelineMath';

const THROTTLE_MS = 80;
const TS_ROUND_SEC = 0.25;

function roundTs(ts: number): number {
  return Math.round(ts / TS_ROUND_SEC) * TS_ROUND_SEC;
}

type CacheEntry = { ts: number; meta: StreamMetadata | null };

const metadataCache = new Map<string, CacheEntry>();

function cacheKey(camera: string, ts: number, date: string, runId: number | null): string {
  return `${camera}:${roundTs(ts)}:${date}:${runId ?? 'none'}`;
}

export function usePlaybackMetadata({
  camera,
  sourceId,
  positionSec,
  runId,
  enabled,
}: {
  camera: string;
  sourceId?: number | null;
  positionSec: number;
  runId: number | null;
  enabled: boolean;
}) {
  const [meta, setMeta] = useState<StreamMetadata | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastFetchKey = useRef<string | null>(null);

  useEffect(() => {
    if (!enabled || !camera || !Number.isFinite(positionSec)) {
      setMeta(null);
      setLoading(false);
      setError(null);
      return;
    }

    const rounded = roundTs(positionSec);
    const eventDate = localDateString(positionSec);
    const key = cacheKey(camera, rounded, eventDate, runId);
    const cached = metadataCache.get(key);
    if (cached) {
      setMeta(cached.meta);
      setError(null);
    }

    const fetchNow = () => {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      lastFetchKey.current = key;
      setLoading(true);
      void playbackApi
        .metadata(camera, rounded, eventDate, runId, {
          signal: ac.signal,
          sourceId: sourceId ?? undefined,
        })
        .then((res) => {
          if (ac.signal.aborted || lastFetchKey.current !== key) return;
          const payload = res.metadata ?? null;
          metadataCache.set(key, { ts: rounded, meta: payload });
          setMeta(payload);
          setError(null);
        })
        .catch((e) => {
          if (isAbortError(e) || ac.signal.aborted) return;
          setError(String(e));
        })
        .finally(() => {
          if (!ac.signal.aborted && lastFetchKey.current === key) setLoading(false);
        });
    };

    if (timerRef.current != null) window.clearTimeout(timerRef.current);
    if (!cached) fetchNow();
    else {
      timerRef.current = window.setTimeout(fetchNow, THROTTLE_MS);
    }

    return () => {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
      abortRef.current?.abort();
    };
  }, [camera, sourceId, positionSec, runId, enabled]);

  return { meta, loading, error };
}
