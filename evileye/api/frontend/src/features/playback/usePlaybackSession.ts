import { useCallback, useEffect, useRef } from 'react';

const KEY = 'evileye.playback.session.v1';
const PERSIST_DEBOUNCE_MS = 300;

export type PlaybackSessionSnapshot = {
  date: string;
  positionSec: number;
  viewFrom: number;
  viewTo: number;
  runId?: number | null;
};

export function readPlaybackSession(): PlaybackSessionSnapshot | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PlaybackSessionSnapshot;
    if (
      typeof parsed?.date !== 'string' ||
      !Number.isFinite(parsed.positionSec) ||
      !Number.isFinite(parsed.viewFrom) ||
      !Number.isFinite(parsed.viewTo)
    ) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function writePlaybackSession(snapshot: PlaybackSessionSnapshot): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(snapshot));
  } catch {
    /* ignore quota / private mode */
  }
}

/** Persist archive date/position/viewport for the browser tab session. */
export function usePlaybackSessionPersist(snapshot: PlaybackSessionSnapshot | null, enabled: boolean) {
  const timerRef = useRef<number | null>(null);
  const persist = useCallback((next: PlaybackSessionSnapshot) => {
    if (timerRef.current != null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      writePlaybackSession(next);
      timerRef.current = null;
    }, PERSIST_DEBOUNCE_MS);
  }, []);

  useEffect(() => {
    if (!enabled || !snapshot) return;
    persist(snapshot);
  }, [enabled, snapshot, persist]);

  useEffect(() => {
    return () => {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
    };
  }, []);
}
