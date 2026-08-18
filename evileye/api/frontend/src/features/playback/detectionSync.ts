import type { PlaybackDetectionItem, StreamMetadataObject } from '../../api';

export const MATCH_SEC = 0.5;
export const SKIP_GAP_SEC = 1.0;
/** Interpolate bbox across found→lost; cap avoids runaway on bad pairing data. */
export const MAX_LERP_SEC = 600.0;

export type FrameSizeLike = { w: number; h: number };

type TrackInterval = {
  foundTs: number;
  lostTs: number;
  found: PlaybackDetectionItem;
  lost: PlaybackDetectionItem;
};

/** Overlay/fetch gate: show objects when this camera has an active track. */
export function shouldShowPlaybackObjects({
  showMetadata,
  atCameraDetection,
  detectionsReady = true,
}: {
  showMetadata: boolean;
  globalTsLength?: number;
  atCameraDetection: boolean;
  atGlobalDetection?: boolean;
  detectionsReady?: boolean;
}): boolean {
  if (!showMetadata || !detectionsReady) return false;
  return atCameraDetection;
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

/** Pair consecutive found→lost events per object_id in timestamp order. */
export function pairTrackIntervals(items: PlaybackDetectionItem[]): TrackInterval[] {
  const byOid = new Map<number, PlaybackDetectionItem[]>();
  for (const it of items) {
    if (!Number.isFinite(it.ts) || it.object_id == null) continue;
    const list = byOid.get(it.object_id) ?? [];
    list.push(it);
    byOid.set(it.object_id, list);
  }

  const intervals: TrackInterval[] = [];
  for (const events of byOid.values()) {
    events.sort((a, b) => a.ts - b.ts);
    let pendingFound: PlaybackDetectionItem | null = null;
    for (const ev of events) {
      if (ev.kind === 'found') {
        pendingFound = ev;
      } else if (ev.kind === 'lost' && pendingFound != null) {
        if (ev.ts >= pendingFound.ts) {
          intervals.push({
            foundTs: pendingFound.ts,
            lostTs: ev.ts,
            found: pendingFound,
            lost: ev,
          });
        }
        pendingFound = null;
      }
    }
  }
  return intervals;
}

function intervalVisibleAt(
  interval: TrackInterval,
  positionSec: number,
  matchSec: number,
  maxLerpSec: number,
): boolean {
  const { foundTs, lostTs } = interval;
  if (Math.abs(foundTs - positionSec) < matchSec) return true;
  if (Math.abs(lostTs - positionSec) < matchSec) return true;
  if (foundTs <= positionSec && positionSec <= lostTs) {
    return lostTs - foundTs <= maxLerpSec;
  }
  return false;
}

/** True on snapshots and inside consecutive found→lost intervals. */
export function hasActiveTrackAt(
  items: PlaybackDetectionItem[],
  positionSec: number,
  matchSec = MATCH_SEC,
  maxLerpSec = MAX_LERP_SEC,
): boolean {
  if (!Number.isFinite(positionSec)) return false;
  for (const it of items) {
    if (!Number.isFinite(it.ts) || it.object_id != null) continue;
    if (Math.abs(it.ts - positionSec) < matchSec) return true;
  }
  if (objectsFromDetectionIndex(items, positionSec, matchSec).length > 0) return true;
  for (const interval of pairTrackIntervals(items)) {
    if (intervalVisibleAt(interval, positionSec, matchSec, maxLerpSec)) return true;
  }
  return false;
}

export function bboxFromIndexBox(
  box: unknown,
  frameSize?: FrameSizeLike | null,
): [number, number, number, number] | null {
  let a = 0;
  let b = 0;
  let c = 0;
  let d = 0;
  if (box && typeof box === 'object' && !Array.isArray(box)) {
    const rec = box as Record<string, unknown>;
    a = Number(rec.x);
    b = Number(rec.y);
    c = Number(rec.width);
    d = Number(rec.height);
    if (![a, b, c, d].every(Number.isFinite)) return null;
    if (Math.max(Math.abs(a), Math.abs(b), Math.abs(c), Math.abs(d)) <= 1.5) {
      return [a, b, a + c, b + d];
    }
    const w = frameSize?.w ?? 0;
    const h = frameSize?.h ?? 0;
    if (w > 0 && h > 0) return [a / w, b / h, (a + c) / w, (b + d) / h];
    return null;
  }
  if (Array.isArray(box) && box.length >= 4) {
    a = Number(box[0]);
    b = Number(box[1]);
    c = Number(box[2]);
    d = Number(box[3]);
    if (![a, b, c, d].every(Number.isFinite)) return null;
    const xyxy = c >= a && d >= b;
    if (Math.max(Math.abs(a), Math.abs(b), Math.abs(c), Math.abs(d)) <= 1.5) {
      return xyxy ? [a, b, c, d] : [a, b, a + c, b + d];
    }
    const w = frameSize?.w ?? 0;
    const h = frameSize?.h ?? 0;
    if (w <= 0 || h <= 0) return null;
    if (xyxy) return [a / w, b / h, c / w, d / h];
    return [a / w, b / h, (a + c) / w, (b + d) / h];
  }
  return null;
}

function lerpBbox(
  start: [number, number, number, number],
  end: [number, number, number, number],
  t: number,
): [number, number, number, number] {
  const u = Math.max(0, Math.min(1, t));
  return [
    start[0] + (end[0] - start[0]) * u,
    start[1] + (end[1] - start[1]) * u,
    start[2] + (end[2] - start[2]) * u,
    start[3] + (end[3] - start[3]) * u,
  ];
}

function itemToObject(
  it: PlaybackDetectionItem,
  bbox: [number, number, number, number],
): StreamMetadataObject {
  return {
    object_id: it.object_id,
    track_id: it.track_id ?? it.object_id,
    global_id: it.global_id,
    class_id: it.class_id ?? undefined,
    class_name: it.class_name,
    conf: it.confidence,
    bbox,
  };
}

/** Immediate overlay objects from snapshots and found→lost intervals. */
export function objectsToOverlayFromIndex(
  items: PlaybackDetectionItem[],
  positionSec: number,
  frameSize?: FrameSizeLike | null,
  matchSec = MATCH_SEC,
  maxLerpSec = MAX_LERP_SEC,
): StreamMetadataObject[] {
  if (!Number.isFinite(positionSec)) return [];
  const out: StreamMetadataObject[] = [];
  const seen = new Set<number | string>();

  const near = objectsFromDetectionIndex(items, positionSec, matchSec);
  for (const it of near) {
    const bbox = bboxFromIndexBox(it.bounding_box, frameSize);
    if (!bbox) continue;
    const key = it.object_id ?? `anon:${it.ts}:${it.kind}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(itemToObject(it, bbox));
  }

  for (const interval of pairTrackIntervals(items)) {
    const oid = interval.found.object_id ?? interval.lost.object_id;
    const key = oid ?? `interval:${interval.foundTs}`;
    if (seen.has(key)) continue;
    if (!intervalVisibleAt(interval, positionSec, matchSec, maxLerpSec)) continue;
    const span = interval.lostTs - interval.foundTs;
    const foundBox = bboxFromIndexBox(interval.found.bounding_box, frameSize);
    const lostBox = bboxFromIndexBox(interval.lost.bounding_box, frameSize);
    if (!foundBox) continue;
    let bbox = foundBox;
    if (span > 1e-9 && lostBox && positionSec > interval.foundTs && positionSec < interval.lostTs) {
      const t = (positionSec - interval.foundTs) / span;
      bbox = lerpBbox(foundBox, lostBox, t);
    } else if (Math.abs(interval.lostTs - positionSec) < matchSec && lostBox) {
      bbox = lostBox;
    }
    seen.add(key);
    out.push(itemToObject(interval.found, bbox));
  }
  return out;
}

export function overlayTimeLabel(positionSec: number): string {
  if (!Number.isFinite(positionSec)) return '';
  const d = new Date(positionSec * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
