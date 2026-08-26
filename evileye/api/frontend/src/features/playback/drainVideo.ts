/** Release browser media resources so Range GETs are cancelled on unmount. */
export function drainVideoElement(video: HTMLVideoElement | null | undefined) {
  if (!video) return;
  try {
    video.pause();
  } catch {
    /* ignore */
  }
  try {
    video.removeAttribute('src');
    video.load();
  } catch {
    /* ignore */
  }
}
