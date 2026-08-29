import { streamStatus } from '../../api';

/** Keep encode demand warm briefly after leaving Live so return is not cold. */
const LEAVE_GRACE_MS = 90_000;
const GRACE_TICK_MS = 5_000;

let graceTimer: number | null = null;
let graceInterval: number | null = null;
let graceRunIds: number[] = [];

function clearGrace() {
  if (graceTimer != null) {
    window.clearTimeout(graceTimer);
    graceTimer = null;
  }
  if (graceInterval != null) {
    window.clearInterval(graceInterval);
    graceInterval = null;
  }
  graceRunIds = [];
}

function tickGrace() {
  for (const rid of graceRunIds) {
    void streamStatus(rid, null).catch(() => undefined);
  }
}

/** Call while Live is mounted — cancels any leave-grace from a prior visit. */
export function cancelPreviewDemandGrace() {
  clearGrace();
}

/**
 * After Live unmounts, keep POSTing stream:status for LEAVE_GRACE_MS so the
 * broker is not empty when the user returns from Playback quickly.
 */
export function startPreviewDemandGrace(runIds: Iterable<number>) {
  clearGrace();
  graceRunIds = [...new Set(Array.from(runIds).filter((id) => Number.isFinite(id)))];
  if (!graceRunIds.length) return;
  tickGrace();
  graceInterval = window.setInterval(tickGrace, GRACE_TICK_MS);
  graceTimer = window.setTimeout(clearGrace, LEAVE_GRACE_MS);
}
