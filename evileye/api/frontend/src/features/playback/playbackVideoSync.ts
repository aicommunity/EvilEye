/** Seek archived video to global timeline position and show frame while paused. */
export function seekPlaybackVideo(
  video: HTMLVideoElement | null,
  positionSec: number,
  segmentStartTs: number,
  opts?: { playing?: boolean; thresholdSec?: number },
): void {
  if (!video) return;
  const local = Math.max(0, positionSec - segmentStartTs);
  const threshold = opts?.thresholdSec ?? (opts?.playing ? 0.35 : 0.03);
  if (Math.abs(video.currentTime - local) <= threshold) return;
  try {
    if (!opts?.playing) video.pause();
    video.currentTime = local;
  } catch {
    /* ignore seek race before metadata loaded */
  }
}
