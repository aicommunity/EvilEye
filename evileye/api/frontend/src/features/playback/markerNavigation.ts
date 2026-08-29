import type { PlaybackDetectionItem, PlaybackEventInterval, PlaybackSegment, StreamMetadata } from '../../api';
import { bboxFromIndexBox, MATCH_SEC, mergeGlobalDetectionTs, overlayTimeLabel } from './detectionSync';
import { isPlayableAtPosition, nearestMarkerTs } from './timelineMath';

export { nearestMarkerTs };

export type StaticFrameSource = {
  ts: number;
  previewPath: string;
  journalType: 'objects' | 'events';
  mode: 'found' | 'lost';
  bbox?: [number, number, number, number];
  label?: string;
  markerKind: 'detection' | 'event';
};

export { mergeGlobalDetectionTs as globalDetectionTs };

export function globalEventStartTs(
  intervals: PlaybackEventInterval[],
  cameraIds: string[],
): number[] {
  const camSet = new Set(cameraIds);
  const set = new Set<number>();
  for (const it of intervals) {
    if (cameraIds.length && it.camera && !camSet.has(it.camera)) continue;
    if (Number.isFinite(it.start_ts)) set.add(it.start_ts);
  }
  return Array.from(set).sort((a, b) => a - b);
}

export function prevEventTs(sorted: number[], beforeSec: number): number | null {
  let prev: number | null = null;
  for (const ts of sorted) {
    if (ts >= beforeSec - 1e-6) break;
    prev = ts;
  }
  return prev;
}

export function nextEventTs(sorted: number[], afterSec: number): number | null {
  for (const ts of sorted) {
    if (ts > afterSec + 1e-6) return ts;
  }
  return null;
}

/** Per-camera static frame only when a marker matches the playhead exactly (no cross-time bleed). */
export function resolveStaticFrameForCamera(
  cameraId: string,
  positionSec: number,
  segments: PlaybackSegment[],
  detections: PlaybackDetectionItem[],
  events: PlaybackEventInterval[],
  matchSec = MATCH_SEC,
): StaticFrameSource | null {
  if (!Number.isFinite(positionSec)) return null;
  if (isPlayableAtPosition({ [cameraId]: segments }, positionSec, cameraId)) return null;

  const exactDet = detections.find(
    (it) => it.preview_path && Number.isFinite(it.ts) && Math.abs(it.ts - positionSec) < matchSec,
  );
  if (exactDet) {
    const mode: 'found' | 'lost' = exactDet.kind === 'lost' ? 'lost' : 'found';
    return {
      ts: exactDet.ts,
      previewPath: String(exactDet.preview_path),
      journalType: 'objects',
      mode,
      markerKind: 'detection',
      label: exactDet.class_name ?? undefined,
    };
  }

  const exactEv = events.find(
    (it) =>
      it.preview_path &&
      Number.isFinite(it.start_ts) &&
      Math.abs(it.start_ts - positionSec) < matchSec,
  );
  if (exactEv) {
    return {
      ts: exactEv.start_ts,
      previewPath: String(exactEv.preview_path),
      journalType: 'events',
      mode: exactEv.preview_mode === 'lost' ? 'lost' : 'found',
      markerKind: 'event',
      label: exactEv.label ?? exactEv.zone_name ?? undefined,
    };
  }

  return null;
}

export function staticFrameToStreamMetadata(
  frame: StaticFrameSource,
  frameSize: { w: number; h: number } | null,
  detectionItems: PlaybackDetectionItem[],
): StreamMetadata | null {
  const objects: StreamMetadata['objects'] = [];
  if (frame.markerKind === 'detection') {
    const match = detectionItems.find(
      (it) => Math.abs(it.ts - frame.ts) < MATCH_SEC && it.preview_path === frame.previewPath,
    );
    const bbox = bboxFromIndexBox(match?.bounding_box ?? null, frameSize);
    if (bbox) {
      objects.push({
        bbox,
        class_name: match?.class_name ?? frame.label ?? null,
        object_id: match?.object_id ?? undefined,
      });
    }
  }
  if (!objects.length && !frame.label) return null;
  return {
    objects,
    overlay: {
      time_label: overlayTimeLabel(frame.ts),
    },
  };
}
