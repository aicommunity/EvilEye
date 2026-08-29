import { describe, expect, it } from 'vitest';
import type { PlaybackDetectionItem, PlaybackEventInterval, PlaybackSegment } from '../../api';
import {
  globalEventStartTs,
  nearestMarkerTs,
  nextEventTs,
  prevEventTs,
  resolveStaticFrameForCamera,
} from './markerNavigation';

describe('markerNavigation', () => {
  const segments: PlaybackSegment[] = [
    { path: 'a.mp4', start_ts: 100, end_ts: 200, duration_ms: 100_000, playable: true },
  ];

  it('nearestMarkerTs prefers closer marker and detection on tie', () => {
    expect(nearestMarkerTs(250, [240, 260], [255])).toBe(255);
    expect(nearestMarkerTs(250, [249], [251])).toBe(249);
  });

  it('globalEventStartTs filters by selected cameras', () => {
    const intervals: PlaybackEventInterval[] = [
      { start_ts: 10, end_ts: 12, event_type: 'zone_events_entered', camera: 'Cam1' },
      { start_ts: 20, end_ts: 22, event_type: 'zone_events_entered', camera: 'Cam2' },
    ];
    expect(globalEventStartTs(intervals, ['Cam1'])).toEqual([10]);
  });

  it('prevEventTs and nextEventTs navigate sorted starts', () => {
    const starts = [100, 200, 300];
    expect(prevEventTs(starts, 250)).toBe(200);
    expect(nextEventTs(starts, 250)).toBe(300);
    expect(prevEventTs(starts, 100)).toBeNull();
    expect(nextEventTs(starts, 300)).toBeNull();
  });

  it('resolveStaticFrameForCamera returns detection at exact playhead only', () => {
    const detections: PlaybackDetectionItem[] = [
      {
        ts: 250,
        kind: 'found',
        object_id: 1,
        preview_path: 'found.jpg',
        bounding_box: { x: 1, y: 2, width: 3, height: 4 },
      },
    ];
    expect(resolveStaticFrameForCamera('Cam1', 250, segments, detections, [])?.previewPath).toBe('found.jpg');
    expect(resolveStaticFrameForCamera('Cam1', 248, segments, detections, [])).toBeNull();
  });

  it('resolveStaticFrameForCamera skips when playable video exists', () => {
    const detections: PlaybackDetectionItem[] = [
      { ts: 150, kind: 'found', object_id: 1, preview_path: 'found.jpg' },
    ];
    expect(resolveStaticFrameForCamera('Cam1', 150, segments, detections, [])).toBeNull();
  });

  it('resolveStaticFrameForCamera shows event only at exact start_ts', () => {
    const events: PlaybackEventInterval[] = [
      {
        start_ts: 248,
        end_ts: 252,
        event_type: 'zone_events_entered',
        preview_path: 'event.jpg',
      },
    ];
    const detections: PlaybackDetectionItem[] = [
      { ts: 200, kind: 'found', object_id: 1, preview_path: 'old.jpg' },
    ];
    expect(resolveStaticFrameForCamera('Cam1', 248, segments, detections, events)?.previewPath).toBe('event.jpg');
    expect(resolveStaticFrameForCamera('Cam1', 249, segments, detections, events)).toBeNull();
  });
});
