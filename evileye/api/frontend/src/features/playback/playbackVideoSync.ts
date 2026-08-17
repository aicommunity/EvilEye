/** Seek archived video to global timeline position. */
import type { PlaybackPlayMode } from '../../api';

export function seekPlaybackVideo(
  video: HTMLVideoElement | null,
  positionSec: number,
  segmentStartTs: number,
  opts?: {
    playing?: boolean;
    playMode?: PlaybackPlayMode;
    scrubbing?: boolean;
    thresholdSec?: number;
  },
): void {
  if (!video) return;
  const local = Math.max(0, positionSec - segmentStartTs);

  if (opts?.playMode === 'detection-sync') {
    if (Math.abs(video.currentTime - local) <= 0.001) return;
    video.pause();
    try {
      video.currentTime = local;
    } catch {
      /* ignore seek race before metadata loaded */
    }
    return;
  }

  if (opts?.scrubbing || !opts?.playing) {
    if (Math.abs(video.currentTime - local) <= (opts?.thresholdSec ?? 0.03)) return;
    video.pause();
    try {
      video.currentTime = local;
    } catch {
      /* ignore seek race before metadata loaded */
    }
    return;
  }

  if (Math.abs(video.currentTime - local) > 1.0) {
    try {
      video.currentTime = local;
    } catch {
      /* ignore seek race before metadata loaded */
    }
  }
}
