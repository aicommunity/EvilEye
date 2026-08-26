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

const lastReloadAt = new WeakMap<HTMLVideoElement, number>();
/** Prevent reload storms that open dozens of Range GETs and freeze the timeline. */
export const RELOAD_MEDIA_COOLDOWN_MS = 2500;

/**
 * Abort current media network activity and re-request the same URL.
 * Cooldown is per element so multi-cam recovery cannot stampede the API.
 */
export function reloadVideoMedia(
  video: HTMLVideoElement | null | undefined,
  opts?: { force?: boolean },
): boolean {
  if (!video) return false;
  const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
  const prev = lastReloadAt.get(video) ?? 0;
  if (!opts?.force && now - prev < RELOAD_MEDIA_COOLDOWN_MS) return false;
  const src = video.getAttribute('src') || video.currentSrc;
  if (!src) return false;
  lastReloadAt.set(video, now);
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
  try {
    video.setAttribute('src', src);
    video.load();
    return true;
  } catch {
    return false;
  }
}
