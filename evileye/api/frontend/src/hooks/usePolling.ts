import { useEffect, useRef } from 'react';

/**
 * Poll callback on an interval; pauses while document is hidden.
 * Optional staggerMs delays the first tick to desync multiple pollers.
 */
export function usePolling(
  callback: () => void | Promise<void>,
  intervalMs: number,
  enabled = true,
  staggerMs = 0,
) {
  const cbRef = useRef(callback);
  cbRef.current = callback;

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let id: number | null = null;
    let staggerTimer: number | null = null;

    const tick = () => {
      if (cancelled || document.hidden) return;
      void cbRef.current();
    };

    const start = () => {
      if (id != null) window.clearInterval(id);
      tick();
      id = window.setInterval(tick, intervalMs);
    };

    const onVisibility = () => {
      if (document.hidden) {
        if (id != null) {
          window.clearInterval(id);
          id = null;
        }
      } else if (!cancelled) {
        start();
      }
    };

    if (staggerMs > 0) {
      staggerTimer = window.setTimeout(start, staggerMs);
    } else {
      start();
    }
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      cancelled = true;
      if (id != null) window.clearInterval(id);
      if (staggerTimer != null) window.clearTimeout(staggerTimer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [intervalMs, enabled, staggerMs]);
}
