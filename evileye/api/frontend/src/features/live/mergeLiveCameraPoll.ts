/** Pure helpers for Live camera list merge / grace (A08). */

export type LiveCameraLike = { run_id: number; source_id?: number | null };

export interface LiveCameraPollDecision<T> {
  cameras: T[];
  lastGood: T[];
  emptyStreak: number;
  cleared: boolean;
}

export const LIVE_CAMERAS_CACHE_KEY = 'state:cameras:current';

/**
 * After `graceEmptyPolls` consecutive successful empty polls, clear the list.
 * Non-empty always wins and resets the streak.
 */
export function mergeLiveCameraPoll<T extends LiveCameraLike>(
  items: T[],
  prev: T[],
  lastGood: T[],
  emptyStreak: number,
  graceEmptyPolls = 2,
): LiveCameraPollDecision<T> {
  if (items.length) {
    return {
      cameras: items,
      lastGood: items,
      emptyStreak: 0,
      cleared: false,
    };
  }
  const nextStreak = emptyStreak + 1;
  if (nextStreak >= graceEmptyPolls) {
    return {
      cameras: [],
      lastGood: [],
      emptyStreak: nextStreak,
      cleared: true,
    };
  }
  // Keep showing last good / prev during grace.
  const keep = prev.length ? prev : lastGood;
  return {
    cameras: keep,
    lastGood,
    emptyStreak: nextStreak,
    cleared: false,
  };
}

/** Reset module-level Live camera grace state + SPA cache on user change. */
export function resetLiveCameraCache(invalidate: (key: string) => void): {
  lastGood: never[];
  emptyStreak: number;
} {
  invalidate(LIVE_CAMERAS_CACHE_KEY);
  return { lastGood: [], emptyStreak: 0 };
}
