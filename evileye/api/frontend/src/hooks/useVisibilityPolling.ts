import { usePolling } from './usePolling';

/**
 * Shared visibility-aware poll budget: pauses when the document is hidden
 * and supports stagger so Live/Journals/Mobile do not hit the API in lockstep.
 */
export function useVisibilityPolling(
  callback: () => void | Promise<void>,
  intervalMs: number,
  enabled = true,
  staggerMs = 0,
) {
  usePolling(callback, intervalMs, enabled, staggerMs);
}
