import type { PlaybackDetectionItem, StreamMetadataObject } from '../../api';

export const MATCH_SEC = 0.5;
export const SKIP_GAP_SEC = 1.0;
/** Show overlay from the nearest snapshot when playhead is within this gap (seconds). */
export const NEARBY_OVERLAY_SEC = 10.0;
/** Interpolate bbox across found→lost; cap avoids runaway on bad pairing data. */
export const MAX_LERP_SEC = 600.0;

export type FrameSizeLike = { w: number; h: number };

/** Overlay/fetch gate: show API objects unless an index exists and this camera is off-track. */
export function shouldShowPlaybackObjects({
  showMetadata,
  globalTsLength,
  atCameraDetection,
  detectionsReady = true,
}: {
  showMetadata: boolean;
  globalTsLength: number;
  atCameraDetection: boolean;
  atGlobalDetection?: boolean;
  detectionsReady?: boolean;
}): boolean {
  if (!showMetadata || !detectionsReady) return false;
  if (globalTsLength === 0) return false;
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

type TrackEnds = {
  foundTs: number | null;
  lostTs: number | null;
  found: PlaybackDetectionItem | null;
  lost: PlaybackDetectionItem | null;
};

function pairTracks(items: PlaybackDetectionItem[]): Map<number, TrackEnds> {
  const byOid = new Map<number, TrackEnds>();
  for (const it of items) {
    if (!Number.isFinite(it.ts) || it.object_id == null) continue;
    let row = byOid.get(it.object_id);
    if (!row) {
      row = { foundTs: null, lostTs: null, found: null, lost: null };
      byOid.set(it.object_id, row);
    }
    if (it.kind === 'found') {
      if (row.foundTs == null || it.ts < row.foundTs) {
        row.foundTs = it.ts;
        row.found = it;
      }
    } else if (row.lostTs == null || it.ts < row.lostTs) {
      row.lostTs = it.ts;
      row.lost = it;
    }
  }
  return byOid;
}

function trackVisibleAt(
  foundTs: number | null,
  lostTs: number | null,
  positionSec: number,
  matchSec: number,
  maxLerpSec: number,
): boolean {
  if (foundTs != null && Math.abs(foundTs - positionSec) < matchSec) return true;
  if (lostTs != null && Math.abs(lostTs - positionSec) < matchSec) return true;
  if (foundTs != null && lostTs != null && foundTs <= positionSec && positionSec <= lostTs) {
    const span = lostTs - foundTs;
    return span <= maxLerpSec;
  }
  return false;
}

function nearestDetectionByOid(
  items: PlaybackDetectionItem[],
  positionSec: number,
  maxSec: number,
): Map<number, PlaybackDetectionItem> {
  const best = new Map<number, { dist: number; item: PlaybackDetectionItem }>();
  for (const it of items) {
    if (!Number.isFinite(it.ts) || it.object_id == null) continue;
    const delta = it.ts - positionSec;
    if (delta < -1e-6 || delta > maxSec) continue;
    const prev = best.get(it.object_id);
    if (!prev || delta < prev.dist - 1e-9 || (Math.abs(delta - prev.dist) < 1e-9 && it.kind === 'found')) {
      best.set(it.object_id, { dist: delta, item: it });
    }
  }
  return new Map(Array.from(best.entries()).map(([oid, row]) => [oid, row.item]));
}

/** True on snapshots, inside found→lost intervals, and near upcoming/recent detections. */
export function hasActiveTrackAt(
  items: PlaybackDetectionItem[],
  positionSec: number,
  matchSec = MATCH_SEC,
  maxLerpSec = MAX_LERP_SEC,
  nearbySec = NEARBY_OVERLAY_SEC,
): boolean {
  if (!Number.isFinite(positionSec)) return false;
  for (const it of items) {
    if (!Number.isFinite(it.ts) || it.object_id != null) continue;
    if (Math.abs(it.ts - positionSec) < matchSec) return true;
  }
  for (const row of pairTracks(items).values()) {
    if (trackVisibleAt(row.foundTs, row.lostTs, positionSec, matchSec, maxLerpSec)) return true;
  }
  return nearestDetectionByOid(items, positionSec, nearbySec).size > 0;
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

/** Immediate overlay objects from the found/lost index while metadata API is in flight. */
export function objectsToOverlayFromIndex(
  items: PlaybackDetectionItem[],
  positionSec: number,
  frameSize?: FrameSizeLike | null,
  matchSec = MATCH_SEC,
  maxLerpSec = MAX_LERP_SEC,
  nearbySec = NEARBY_OVERLAY_SEC,
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

  for (const [oid, row] of pairTracks(items)) {
    if (seen.has(oid)) continue;
    if (row.foundTs == null || row.lostTs == null) continue;
    if (row.foundTs > positionSec || positionSec > row.lostTs) continue;
    const span = row.lostTs - row.foundTs;
    if (span > maxLerpSec || span <= 1e-9) continue;
    const foundBox = bboxFromIndexBox(row.found?.bounding_box, frameSize);
    const lostBox = bboxFromIndexBox(row.lost?.bounding_box, frameSize);
    if (!foundBox) continue;
    const t = (positionSec - row.foundTs) / span;
    const bbox = lostBox ? lerpBbox(foundBox, lostBox, t) : foundBox;
    seen.add(oid);
    out.push(itemToObject(row.found ?? row.lost!, bbox));
  }

  for (const [oid, it] of nearestDetectionByOid(items, positionSec, nearbySec)) {
    if (seen.has(oid)) continue;
    const bbox = bboxFromIndexBox(it.bounding_box, frameSize);
    if (!bbox) continue;
    seen.add(oid);
    out.push(itemToObject(it, bbox));
  }
  return out;
}

export function overlayTimeLabel(positionSec: number): string {
  if (!Number.isFinite(positionSec)) return '';
  const d = new Date(positionSec * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
