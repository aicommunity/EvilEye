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

/** Backoff after media error (503 shed / aborted Range) — avoid stampeding the API. */
export const ERROR_RELOAD_BACKOFFS_MS = [1000, 2000, 5000] as const;
const errorBackoffStep = new WeakMap<HTMLVideoElement, number>();

/** MEDIA_ERR_SRC_NOT_SUPPORTED / NETWORK_NO_SOURCE — same URL retries are zombie loops. */
export const MEDIA_ERR_SRC_NOT_SUPPORTED = 4;
export const SAME_SRC_ERROR_GIVE_UP = 3;

type SameSrcErrorState = { src: string; count: number };
const sameSrcErrors = new WeakMap<HTMLVideoElement, SameSrcErrorState>();

export function resetErrorMediaBackoff(video: HTMLVideoElement | null | undefined) {
  if (!video) return;
  errorBackoffStep.delete(video);
  sameSrcErrors.delete(video);
}

export function noteSameSrcMediaError(
  video: HTMLVideoElement | null | undefined,
  src: string | null | undefined,
  code: number | null | undefined,
): { count: number; giveUp: boolean } {
  if (!video || !src) return { count: 0, giveUp: false };
  const hard =
    code === MEDIA_ERR_SRC_NOT_SUPPORTED || video.networkState === HTMLMediaElement.NETWORK_NO_SOURCE;
  if (!hard) {
    return { count: sameSrcErrors.get(video)?.count ?? 0, giveUp: false };
  }
  const prev = sameSrcErrors.get(video);
  const count = prev && prev.src === src ? prev.count + 1 : 1;
  sameSrcErrors.set(video, { src, count });
  return { count, giveUp: count >= SAME_SRC_ERROR_GIVE_UP };
}

/**
 * Schedule a cooldown-aware media reload with increasing delay after errors.
 * Returns the timer id (caller should clear on cleanup / successful canplay).
 */
export function scheduleErrorMediaReload(
  video: HTMLVideoElement | null | undefined,
  onReloaded?: () => void,
): number | null {
  if (!video || typeof window === 'undefined') return null;
  const step = errorBackoffStep.get(video) ?? 0;
  const delay =
    ERROR_RELOAD_BACKOFFS_MS[Math.min(step, ERROR_RELOAD_BACKOFFS_MS.length - 1)] ?? 5000;
  errorBackoffStep.set(video, step + 1);
  return window.setTimeout(() => {
    if (reloadVideoMedia(video)) {
      onReloaded?.();
    }
  }, delay);
}

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
