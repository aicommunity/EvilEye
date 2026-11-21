import type { StateCamera } from '../../api';

/** Enter stale when effective frame age exceeds this (seconds). */
export const LIVE_STALE_ENTER_SEC = 12;
/** Leave stale (back to live) only when age drops below this (hysteresis). */
export const LIVE_STALE_EXIT_SEC = 5;
/** @deprecated Prefer LIVE_STALE_ENTER_SEC; kept for callers/tests. */
export const LIVE_STALE_SEC = LIVE_STALE_ENTER_SEC;

export type PreviewMode = 'live' | 'snapshot' | 'stale' | 'error' | 'offline';

export type PreviewHealthOpts = {
  /** Age in seconds derived from the latest WS preview frame timestamp. */
  previewFrameAgeSec?: number | null;
  /** Wall-clock ms when `/state/cameras` response was last applied in the UI. */
  camerasPolledAtMs?: number;
  /**
   * Previous resolved mode for age hysteresis. Without it, ENTER threshold is used
   * (avoids green↔yellow flicker around the boundary).
   */
  previousMode?: PreviewMode;
};

/** Estimate current preview frame age using WS timestamps and/or last API poll. */
export function effectiveFrameAgeSec(
  camera: StateCamera,
  opts?: PreviewHealthOpts,
): number | null {
  const nowMs = Date.now();
  let apiAge: number | null =
    camera.last_frame_age_sec != null ? Number(camera.last_frame_age_sec) : null;
  if (apiAge != null && opts?.camerasPolledAtMs != null) {
    apiAge += Math.max(0, (nowMs - opts.camerasPolledAtMs) / 1000);
  }

  const wsAge = opts?.previewFrameAgeSec;
  if (wsAge != null && apiAge != null) return Math.min(wsAge, apiAge);
  return wsAge ?? apiAge;
}

export function previewFrameAgeSecFromTs(tsSec: number | undefined | null, nowMs: number = Date.now()): number | null {
  if (tsSec == null || !Number.isFinite(tsSec)) return null;
  return Math.max(0, nowMs / 1000 - tsSec);
}

function staleByAge(age: number | null, previousMode?: PreviewMode): boolean {
  if (age == null) return false;
  const wasStale = previousMode === 'stale' || previousMode === 'error';
  if (wasStale) return age >= LIVE_STALE_EXIT_SEC;
  return age > LIVE_STALE_ENTER_SEC;
}

export function resolvePreviewMode(
  camera: StateCamera,
  previewError: boolean,
  opts?: PreviewHealthOpts,
): PreviewMode {
  if (camera.run_state !== 'running') return 'offline';
  if (previewError) return 'error';
  if (camera.reconnecting === true) return 'stale';

  const wsAge = opts?.previewFrameAgeSec;
  const age = effectiveFrameAgeSec(camera, opts);
  const ageStale = staleByAge(age, opts?.previousMode);

  // `preview_available` comes from `/state/cameras` polling and can lag behind WS preview.
  // If we have a fresh WS preview age, prefer that over potentially stale API flags.
  const wsHasFreshness = wsAge != null && Number.isFinite(wsAge);
  const previewAvailableOk = camera.preview_available !== false || wsHasFreshness;

  if (!previewAvailableOk || ageStale || camera.is_working === false) {
    return 'stale';
  }
  return 'live';
}
