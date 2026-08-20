/** Seek archived video to global timeline position. */
export const PAUSED_SEEK_THRESHOLD_SEC = 1 / 30;

let playbackClockOwner: string | null = null;

export function resetPlaybackClockOwner(): void {
  playbackClockOwner = null;
}

/**
 * First ready camera owns the shared playhead.
 * Do not clear ownership on brief `seeking` — that lets another camera steal the clock
 * and drives multi-cam A/B oscillation (frame + overlay flicker).
 */
export function shouldEmitPlaybackClock(ownerId: string, video: HTMLVideoElement): boolean {
  if (video.readyState < 2) {
    if (playbackClockOwner === ownerId) playbackClockOwner = null;
    return false;
  }
  if (video.seeking) {
    // Keep lock, but do not emit mid-seek.
    return false;
  }
  if (playbackClockOwner == null) playbackClockOwner = ownerId;
  return playbackClockOwner === ownerId;
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
  },
): void {
  if (!video) return;
  const clampedPosition =
    opts?.segmentEndTs != null ? Math.min(Math.max(positionSec, segmentStartTs), Math.max(segmentStartTs, opts.segmentEndTs - 0.001)) : positionSec;
  const local = Math.max(0, clampedPosition - segmentStartTs);
  const paused = Boolean(opts?.scrubbing) || !opts?.playing;
  // While playing, tolerate larger drift so follower cameras do not thrash seeks.
  const threshold = opts?.thresholdSec ?? (paused ? PAUSED_SEEK_THRESHOLD_SEC : 1.0);

  if (video.seeking) return;
  if (Math.abs(video.currentTime - local) <= threshold) return;
  try {
    video.currentTime = local;
  } catch {
    /* ignore seek race before metadata loaded */
  }
}
