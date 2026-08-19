/** Seek archived video to global timeline position. */
export const PAUSED_SEEK_THRESHOLD_SEC = 1 / 30;

let playbackClockOwner: string | null = null;

export function resetPlaybackClockOwner(): void {
  playbackClockOwner = null;
}

/** First camera that is ready and not seeking owns the shared playhead. */
export function shouldEmitPlaybackClock(ownerId: string, video: HTMLVideoElement): boolean {
  if (video.seeking || video.readyState < 2) {
    if (playbackClockOwner === ownerId) playbackClockOwner = null;
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
  },
): void {
  if (!video) return;
  const local = Math.max(0, positionSec - segmentStartTs);
  const paused = Boolean(opts?.scrubbing) || !opts?.playing;
  const threshold = opts?.thresholdSec ?? (paused ? PAUSED_SEEK_THRESHOLD_SEC : 1.0);

  if (Math.abs(video.currentTime - local) <= threshold) return;
  try {
    video.currentTime = local;
  } catch {
    /* ignore seek race before metadata loaded */
  }
}
