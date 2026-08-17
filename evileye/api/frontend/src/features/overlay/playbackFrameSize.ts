import type { FrameSize, PlaybackCamera } from '../../api';

/** Frame size for metadata API — logical/display frame, not parent MP4 for split. */
export function resolvePlaybackFrameSize(
  camera: PlaybackCamera | undefined,
  videoSize: FrameSize | null,
): FrameSize | null {
  const logical = camera?.logical_frame_size;
  if (logical && logical.w > 0 && logical.h > 0) {
    return { w: logical.w, h: logical.h };
  }
  if (camera?.split && camera.src_coords?.length === 4) {
    const w = camera.src_coords[2];
    const h = camera.src_coords[3];
    if (w > 0 && h > 0) return { w, h };
  }
  return videoSize && videoSize.w > 0 && videoSize.h > 0 ? videoSize : null;
}
