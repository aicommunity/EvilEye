import { useMemo } from 'react';
import type { PlaybackDetectionItem, PlaybackEventInterval, PlaybackSegment } from '../../api';
import { resolveStaticFrameForCamera, type StaticFrameSource } from './markerNavigation';

export function useStaticFrameForCamera({
  cameraId,
  positionSec,
  segments,
  detections,
  events,
  enabled = true,
}: {
  cameraId: string;
  positionSec: number;
  segments: PlaybackSegment[];
  detections: PlaybackDetectionItem[];
  events: PlaybackEventInterval[];
  enabled?: boolean;
}): StaticFrameSource | null {
  return useMemo(() => {
    if (!enabled) return null;
    return resolveStaticFrameForCamera(cameraId, positionSec, segments, detections, events);
  }, [cameraId, positionSec, segments, detections, events, enabled]);
}
