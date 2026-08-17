import type { PlaybackDetectionItem } from '../../api';

export const MATCH_SEC = 0.15;
export const DETECTION_STEP_INTERVAL_MS = 800;

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
