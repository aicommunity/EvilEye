/** Seek archived video to global timeline position. */
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
  const threshold = opts?.thresholdSec ?? (paused ? 0 : 1.0);

  if (Math.abs(video.currentTime - local) <= threshold) return;
  if (paused) video.pause();
  try {
    video.currentTime = local;
  } catch {
    /* ignore seek race before metadata loaded */
  }
}
