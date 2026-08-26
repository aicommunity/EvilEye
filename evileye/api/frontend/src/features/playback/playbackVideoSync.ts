/** Seek archived video to global timeline position. */
import {
  isPlaybackDebugEnabled,
  playbackDebugInc,
  playbackDebugSetMeta,
} from './playbackDebug';

export const PAUSED_SEEK_THRESHOLD_SEC = 1 / 30;
/** Keep a small lead-in from EOF — seeking to exact duration often hangs decoders. */
export const PLAYBACK_EOF_PAD_SEC = 0.05;
/** After this, allow force-seek even while `video.seeking` (decoder hang recovery). */
export const SEEKING_STUCK_MS = 1800;
/** Drop shared clock ownership if the owner cannot emit for this long. */
export const CLOCK_OWNER_STALE_MS = 2500;
/** Ignore stale video clock right after scrubbing clears (anti-rollback). */
export const CLOCK_GRACE_MS = 400;

let playbackClockOwner: string | null = null;
let ownerBlockSince: number | null = null;
const seekingSince = new WeakMap<HTMLVideoElement, number>();

/** Injectable clock for unit tests. */
let nowMs: () => number = () =>
  typeof performance !== 'undefined' ? performance.now() : Date.now();

export function setPlaybackSyncNow(fn: (() => number) | null): void {
  nowMs = fn ?? (() => (typeof performance !== 'undefined' ? performance.now() : Date.now()));
}

export function resetPlaybackClockOwner(): void {
  playbackClockOwner = null;
  ownerBlockSince = null;
  if (isPlaybackDebugEnabled()) playbackDebugSetMeta({ clockOwnerId: null });
}

export function getPlaybackClockOwner(): string | null {
  return playbackClockOwner;
}

export function seekingAgeMs(video: HTMLVideoElement): number {
  if (!video.seeking) {
    seekingSince.delete(video);
    return 0;
  }
  const started = seekingSince.get(video);
  if (started == null) {
    seekingSince.set(video, nowMs());
    return 0;
  }
  return nowMs() - started;
}

function noteSeekingState(video: HTMLVideoElement): void {
  if (video.seeking) {
    if (!seekingSince.has(video)) seekingSince.set(video, nowMs());
  } else {
    seekingSince.delete(video);
  }
}

/**
 * First ready camera owns the shared playhead.
 * Do not clear ownership on brief `seeking` — that lets another camera steal the clock
 * and drives multi-cam A/B oscillation (frame + overlay flicker).
 * Stale owner (seeking / blocked emit too long) is cleared so recovery can continue.
 */
export function shouldEmitPlaybackClock(ownerId: string, video: HTMLVideoElement): boolean {
  noteSeekingState(video);
  if (video.readyState < 2) {
    if (playbackClockOwner === ownerId) {
      playbackClockOwner = null;
      ownerBlockSince = null;
    }
    return false;
  }
  if (video.seeking) {
    if (playbackClockOwner === ownerId || playbackClockOwner == null) {
      if (ownerBlockSince == null) ownerBlockSince = nowMs();
      const blocked = nowMs() - ownerBlockSince;
      if (blocked >= CLOCK_OWNER_STALE_MS) {
        playbackClockOwner = null;
        ownerBlockSince = null;
        if (isPlaybackDebugEnabled()) playbackDebugSetMeta({ clockOwnerId: null });
      }
    }
    // Keep lock briefly, but do not emit mid-seek.
    return false;
  }
  // Only the healthy owner clears the stale timer — followers must not reset it.
  if (playbackClockOwner === ownerId) {
    ownerBlockSince = null;
  }
  if (playbackClockOwner == null) playbackClockOwner = ownerId;
  if (isPlaybackDebugEnabled()) playbackDebugSetMeta({ clockOwnerId: playbackClockOwner });
  const ok = playbackClockOwner === ownerId;
  if (ok) playbackDebugInc('clockEmits');
  return ok;
}

/** Effective media end in global timeline seconds (index end ∩ decoded duration). */
export function effectiveSegmentEndTs(
  segmentStartTs: number,
  segmentEndTs: number | undefined,
  video: HTMLVideoElement | null | undefined,
): number | undefined {
  const indexEnd = segmentEndTs != null && segmentEndTs > segmentStartTs ? segmentEndTs : undefined;
  const mediaEnd =
    video && Number.isFinite(video.duration) && video.duration > 0
      ? segmentStartTs + video.duration
      : undefined;
  if (indexEnd == null) return mediaEnd;
  if (mediaEnd == null) return indexEnd;
  return Math.min(indexEnd, mediaEnd);
}

export function seekPlaybackVideo(
  video: HTMLVideoElement | null,
  positionSec: number,
  segmentStartTs: number,
  opts?: {
    playing?: boolean;
    scrubbing?: boolean;
    thresholdSec?: number;
    segmentEndTs?: number;
    /** Force assign even if seeking and not scrubbing (watchdog). */
    force?: boolean;
  },
): void {
  if (!video) return;
  playbackDebugInc('seekPlaybackCalls');
  noteSeekingState(video);
  const endTs = effectiveSegmentEndTs(segmentStartTs, opts?.segmentEndTs, video);
  const clampedPosition =
    endTs != null ? Math.min(Math.max(positionSec, segmentStartTs), endTs - PLAYBACK_EOF_PAD_SEC) : positionSec;
  if (endTs != null && positionSec > endTs - PLAYBACK_EOF_PAD_SEC) {
    playbackDebugInc('eofClampHits');
  }
  let local = Math.max(0, clampedPosition - segmentStartTs);
  if (Number.isFinite(video.duration) && video.duration > 0) {
    local = Math.min(local, Math.max(0, video.duration - PLAYBACK_EOF_PAD_SEC));
  }
  const paused = Boolean(opts?.scrubbing) || !opts?.playing;
  // While playing, tolerate larger drift so follower cameras do not thrash seeks.
  const threshold = opts?.thresholdSec ?? (paused ? PAUSED_SEEK_THRESHOLD_SEC : 1.0);

  const age = seekingAgeMs(video);
  const stuck = age >= SEEKING_STUCK_MS;
  // Scrubbing / force / stuck must win over an in-flight seek — otherwise playhead pins.
  if (video.seeking && !opts?.scrubbing && !opts?.force && !stuck) {
    playbackDebugInc('seekPlaybackSkippedSeeking');
    return;
  }
  if (video.seeking && (opts?.force || stuck) && !opts?.scrubbing) {
    playbackDebugInc('seekForceOverride');
  }
  if (Math.abs(video.currentTime - local) <= threshold && !opts?.force && !stuck) return;
  try {
    video.currentTime = local;
    // Treat as a new seek attempt for age tracking.
    seekingSince.set(video, nowMs());
  } catch {
    /* ignore seek race before metadata loaded */
  }
}

/** True when playhead is past the real decoded media (index can overrun the mp4). */
export function isPastDecodedEof(
  video: HTMLVideoElement | null | undefined,
  positionSec: number,
  segmentStartTs: number,
  padSec = 0.25,
): boolean {
  if (!video || !(Number.isFinite(video.duration) && video.duration > 0)) return false;
  const past = positionSec > segmentStartTs + video.duration + padSec;
  if (past) playbackDebugInc('pastEofHits');
  return past;
}
