/** Seek archived video to global timeline position. */
export const PAUSED_SEEK_THRESHOLD_SEC = 1 / 30;

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
  if (opts?.scrubbing) video.pause();
  try {
    video.currentTime = local;
  } catch {
    /* ignore seek race before metadata loaded */
  }
}
