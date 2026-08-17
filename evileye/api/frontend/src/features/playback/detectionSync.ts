import type { PlaybackDetectionItem } from '../../api';

export const MATCH_SEC = 0.5;
export const SKIP_GAP_SEC = 1.0;

/** Overlay/fetch gate: show API objects unless an index exists and we are off every snapshot. */
export function shouldShowPlaybackObjects({
  showMetadata,
  globalTsLength,
  atCameraDetection,
  atGlobalDetection,
}: {
  showMetadata: boolean;
  globalTsLength: number;
  atCameraDetection: boolean;
  atGlobalDetection: boolean;
}): boolean {
  if (!showMetadata) return false;
  if (globalTsLength === 0) return true;
  return atCameraDetection || atGlobalDetection;
}

/** Skip empty frames only when the next snapshot is close (active-track gap). */
export function shouldSkipToDetection(
  positionSec: number,
  nextTs: number | null,
  gapSec = SKIP_GAP_SEC,
): boolean {
  if (nextTs == null || !Number.isFinite(positionSec) || !Number.isFinite(nextTs)) return false;
  const gap = nextTs - positionSec;
  return gap > 1e-6 && gap < gapSec;
}

export function mergeGlobalDetectionTs(
  byCamera: Record<string, PlaybackDetectionItem[]>,
): number[] {
  const set = new Set<number>();
  for (const items of Object.values(byCamera)) {
    for (const it of items) {
      if (Number.isFinite(it.ts)) set.add(it.ts);
    }
  }
  return Array.from(set).sort((a, b) => a - b);
}

export function detectionTsAtOrNull(
  sortedTs: number[],
  positionSec: number,
  matchSec = MATCH_SEC,
): number | null {
  for (const ts of sortedTs) {
    if (Math.abs(ts - positionSec) < matchSec) return ts;
  }
  return null;
}

export function nextDetectionTs(sortedTs: number[], afterSec: number): number | null {
  for (const ts of sortedTs) {
    if (ts > afterSec + 1e-6) return ts;
  }
  return null;
}

export function prevDetectionTs(sortedTs: number[], beforeSec: number): number | null {
  let prev: number | null = null;
  for (const ts of sortedTs) {
    if (ts >= beforeSec - 1e-6) break;
    prev = ts;
  }
  return prev;
}

export function objectsFromDetectionIndex(
  items: PlaybackDetectionItem[],
  positionSec: number,
  matchSec = MATCH_SEC,
): PlaybackDetectionItem[] {
  return items.filter((it) => Math.abs(it.ts - positionSec) < matchSec);
}

export function hasDetectionAt(
  sortedTs: number[],
  positionSec: number,
  matchSec = MATCH_SEC,
): boolean {
  return detectionTsAtOrNull(sortedTs, positionSec, matchSec) != null;
}

/** True while playhead is inside a found→lost interval (or on a lone snapshot). */
export function hasActiveTrackAt(
  items: PlaybackDetectionItem[],
  positionSec: number,
  matchSec = MATCH_SEC,
): boolean {
  if (!Number.isFinite(positionSec)) return false;
  const found = new Map<number, number>();
  const lost = new Map<number, number>();
  for (const it of items) {
    if (!Number.isFinite(it.ts)) continue;
    if (it.object_id == null) {
      if (Math.abs(it.ts - positionSec) < matchSec) return true;
      continue;
    }
    if (it.kind === 'found') {
      const prev = found.get(it.object_id);
      if (prev == null || it.ts < prev) found.set(it.object_id, it.ts);
    } else {
      const prev = lost.get(it.object_id);
      if (prev == null || it.ts < prev) lost.set(it.object_id, it.ts);
    }
  }
  for (const oid of new Set([...found.keys(), ...lost.keys()])) {
    const f = found.get(oid);
    const l = lost.get(oid);
    if (f != null && l != null && f <= positionSec && positionSec <= l) return true;
    if (f != null && Math.abs(f - positionSec) < matchSec) return true;
    if (l != null && Math.abs(l - positionSec) < matchSec) return true;
  }
  return false;
}
