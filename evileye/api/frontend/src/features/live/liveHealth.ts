import type { StateCamera } from '../../api';

export const LIVE_STALE_SEC = 5;

export type PreviewHealthOpts = {
  /** Age in seconds derived from the latest WS preview frame timestamp. */
  previewFrameAgeSec?: number | null;
  /** Wall-clock ms when `/state/cameras` response was last applied in the UI. */
  camerasPolledAtMs?: number;
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

export type PreviewMode = 'live' | 'snapshot' | 'stale' | 'error' | 'offline';

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
  const staleByAge = age != null && age > LIVE_STALE_SEC;

  // `preview_available` comes from `/state/cameras` polling and can lag behind WS preview.
  // If we have a fresh WS preview age, prefer that over potentially stale API flags.
  const wsHasFreshness = wsAge != null && Number.isFinite(wsAge);
  const previewAvailableOk = camera.preview_available !== false || wsHasFreshness;

  if (!previewAvailableOk || staleByAge || camera.is_working === false) {
    return 'stale';
  }
  return 'live';
}
