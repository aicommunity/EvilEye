import { useEffect, useRef, useState } from 'react';
import { isAbortError, playbackApi, PLAYBACK_DETECTION_MATCH_SEC, type FrameSize, type StreamMetadata } from '../../api';
import { localDateString } from './timelineMath';

const FETCH_DEBOUNCE_MS = 130;
const TS_ROUND_SEC = PLAYBACK_DETECTION_MATCH_SEC;
const APPLY_SLACK_SEC = 0.3;

function roundTs(ts: number): number {
  return Math.round(ts / TS_ROUND_SEC) * TS_ROUND_SEC;
}

type CacheEntry = { ts: number; meta: StreamMetadata | null };

const metadataCache = new Map<string, CacheEntry>();

function hasFrameSize(frameSize: FrameSize | null | undefined): frameSize is FrameSize {
  return Boolean(frameSize && frameSize.w > 0 && frameSize.h > 0);
}

function cacheKey(
  camera: string,
  ts: number,
  date: string,
  runId: number | null,
  frameSize: FrameSize,
): string {
  return `${camera}:${roundTs(ts)}:${date}:${runId ?? 'none'}:${frameSize.w}x${frameSize.h}`;
}

export function usePlaybackMetadata({
  camera,
  sourceId,
  positionSec,
  runId,
  enabled,
  frameSize,
  playing = false,
  hasDetectionAtPosition = true,
}: {
  camera: string;
  sourceId?: number | null;
  positionSec: number;
  runId: number | null;
  enabled: boolean;
  frameSize?: FrameSize | null;
  playing?: boolean;
  hasDetectionAtPosition?: boolean;
}) {
  const [meta, setMeta] = useState<StreamMetadata | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const inflightKeyRef = useRef<string | null>(null);
  const roundedRef = useRef(0);

  useEffect(() => {
    roundedRef.current = roundTs(positionSec);
  }, [positionSec]);

  useEffect(() => {
    if (!enabled || !camera || !Number.isFinite(positionSec)) {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
      timerRef.current = null;
      abortRef.current?.abort();
      abortRef.current = null;
      inflightKeyRef.current = null;
      setMeta(null);
      setLoading(false);
      setError(null);
      return;
    }
    if (!hasFrameSize(frameSize)) {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
      timerRef.current = null;
      abortRef.current?.abort();
      abortRef.current = null;
      inflightKeyRef.current = null;
      setMeta(null);
      setLoading(false);
      setError(null);
      return;
    }
    if (!hasDetectionAtPosition) {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
      timerRef.current = null;
      abortRef.current?.abort();
      abortRef.current = null;
      inflightKeyRef.current = null;
      setMeta(null);
      setLoading(false);
      setError(null);
      return;
    }

    const rounded = roundTs(positionSec);
    const eventDate = localDateString(positionSec);
    const key = cacheKey(camera, rounded, eventDate, runId, frameSize);
    const cached = metadataCache.get(key);
    if (cached) {
      setMeta(cached.meta);
      setLoading(false);
      setError(null);
      return;
    }

    setError(null);

    const fetchNow = () => {
      if (inflightKeyRef.current === key) return;
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      inflightKeyRef.current = key;
      setLoading(true);
      void playbackApi
        .metadata(camera, rounded, eventDate, runId, {
          signal: ac.signal,
          sourceId: sourceId ?? undefined,
          frameSize,
          matchSec: PLAYBACK_DETECTION_MATCH_SEC,
        })
        .then((res) => {
          if (ac.signal.aborted) return;
          const payload = res.metadata ?? null;
          const payloadTs = payload?.ts != null ? Number(payload.ts) : rounded;
          if (Math.abs(payloadTs - roundedRef.current) >= APPLY_SLACK_SEC) return;
          metadataCache.set(key, { ts: rounded, meta: payload });
          setMeta(payload);
          setError(null);
        })
        .catch((e) => {
          if (isAbortError(e) || ac.signal.aborted) return;
          setError(String(e));
        })
        .finally(() => {
          if (inflightKeyRef.current === key) {
            inflightKeyRef.current = null;
            setLoading(false);
          }
        });
    };

    if (timerRef.current != null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(fetchNow, FETCH_DEBOUNCE_MS);

    return () => {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
      timerRef.current = null;
    };
  }, [
    camera,
    sourceId,
    roundTs(positionSec),
    runId,
    enabled,
    frameSize?.w,
    frameSize?.h,
    playing,
    hasDetectionAtPosition,
  ]);

  return { meta, loading, error };
}
