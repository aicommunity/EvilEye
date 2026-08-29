import {
  hasAnyPlayableAtPosition,
  snapUnionPositionToPlayable,
} from './timelineMath';
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
  segmentsByCam: Record<string, PlaybackSegment[]>,
  opts: {
    merge?: boolean;
    initialT: number | null;
    getPosition: () => number;
    seek: (sec: number, seekOpts?: SeekOptions) => void;
    guard: UserSeekGuard;
  },
): void {
  if (opts.merge || !Object.keys(segmentsByCam).length) return;
  if (!opts.guard.shouldApplyPostLoadSnap(opts.initialT)) return;
  const target = opts.initialT != null ? opts.initialT : opts.getPosition();
  const snapped = snapUnionPositionToPlayable(segmentsByCam, target);
  if (Math.abs(snapped - opts.getPosition()) > 0.5) {
    opts.seek(snapped, { mode: 'playable', pauseIfNoVideo: false });
  }
}

export type SeekMode = 'marker' | 'playable';

export type SeekOptions = {
  mode?: SeekMode;
  pauseIfNoVideo?: boolean;
};

/** User seek: marker mode keeps gap position; playable mode snaps to MP4 union. */
export function resolveUserSeekTarget(
  sec: number,
  segmentsByCam?: Record<string, PlaybackSegment[]>,
  mode: SeekMode = 'marker',
): number {
  if (!segmentsByCam || !Object.keys(segmentsByCam).length) return sec;
  if (mode === 'marker') return sec;
  if (hasAnyPlayableAtPosition(segmentsByCam, sec)) return sec;
  return snapUnionPositionToPlayable(segmentsByCam, sec);
}
