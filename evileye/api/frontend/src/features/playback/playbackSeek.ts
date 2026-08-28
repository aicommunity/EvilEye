import { snapPositionToPlayable } from './timelineMath';
import type { PlaybackSegment } from '../../api';

export const POST_LOAD_SNAP_GRACE_MS = 5000;
export const SEEK_SETTLE_HOLD_MS = 250;

export type UserSeekGuard = {
  markUserSeek: () => void;
  shouldApplyPostLoadSnap: (initialT: number | null) => boolean;
};

export function createUserSeekGuard(): UserSeekGuard {
  let lastUserSeekAt = 0;
  return {
    markUserSeek() {
      lastUserSeekAt = Date.now();
    },
    shouldApplyPostLoadSnap(initialT: number | null) {
      if (initialT != null) return true;
      return Date.now() - lastUserSeekAt > POST_LOAD_SNAP_GRACE_MS;
    },
  };
}

export function applyPostLoadSnapIfNeeded(
  allSegs: PlaybackSegment[],
  opts: {
    merge?: boolean;
    initialT: number | null;
    getPosition: () => number;
    seek: (sec: number) => void;
    guard: UserSeekGuard;
  },
): void {
  if (opts.merge || !allSegs.length) return;
  if (!opts.guard.shouldApplyPostLoadSnap(opts.initialT)) return;
  const target = opts.initialT != null ? opts.initialT : opts.getPosition();
  const snapped = snapPositionToPlayable(allSegs, target);
  if (Math.abs(snapped - opts.getPosition()) > 0.5) opts.seek(snapped);
}

/** User click: wall-clock intent only (detection snap happens in Timeline). */
export function resolveUserSeekTarget(sec: number): number {
  return sec;
}
