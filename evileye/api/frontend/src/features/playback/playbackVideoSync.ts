/** Seek archived video to global timeline position. */
export const PAUSED_SEEK_THRESHOLD_SEC = 1 / 30;
/** Keep a small lead-in from EOF — seeking to exact duration often hangs decoders. */
export const PLAYBACK_EOF_PAD_SEC = 0.05;

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
  },
): void {
  if (!video) return;
  const endTs = effectiveSegmentEndTs(segmentStartTs, opts?.segmentEndTs, video);
  const clampedPosition =
    endTs != null ? Math.min(Math.max(positionSec, segmentStartTs), endTs - PLAYBACK_EOF_PAD_SEC) : positionSec;
  let local = Math.max(0, clampedPosition - segmentStartTs);
  if (Number.isFinite(video.duration) && video.duration > 0) {
    local = Math.min(local, Math.max(0, video.duration - PLAYBACK_EOF_PAD_SEC));
  }
  const paused = Boolean(opts?.scrubbing) || !opts?.playing;
  // While playing, tolerate larger drift so follower cameras do not thrash seeks.
  const threshold = opts?.thresholdSec ?? (paused ? PAUSED_SEEK_THRESHOLD_SEC : 1.0);

  // Scrubbing must win over an in-flight seek — otherwise playhead pins to the old time.
  if (video.seeking && !opts?.scrubbing) return;
  if (Math.abs(video.currentTime - local) <= threshold) return;
  try {
    video.currentTime = local;
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
  return positionSec > segmentStartTs + video.duration + padSec;
}
