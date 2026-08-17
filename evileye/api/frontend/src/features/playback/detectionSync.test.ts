import { describe, expect, it } from 'vitest';
import {
  bboxFromIndexBox,
  hasActiveTrackAt,
  objectsToOverlayFromIndex,
  shouldSkipToDetection,
  shouldShowPlaybackObjects,
  SKIP_GAP_SEC,
} from './detectionSync';

describe('shouldSkipToDetection', () => {
  it('skips when the next snapshot is within the gap', () => {
    expect(shouldSkipToDetection(100, 100.4, 1.0)).toBe(true);
  });

  it('does not skip when the next snapshot is far', () => {
    expect(shouldSkipToDetection(100, 105, 1.0)).toBe(false);
  });

  it('shows objects when index is empty (metadata API fallback)', () => {
    expect(
      shouldShowPlaybackObjects({
        showMetadata: true,
        globalTsLength: 0,
        atCameraDetection: false,
        atGlobalDetection: true,
      }),
    ).toBe(true);
  });

  it('hides objects when index exists and this camera is off-track', () => {
    expect(
      shouldShowPlaybackObjects({
        showMetadata: true,
        globalTsLength: 3,
        atCameraDetection: false,
        atGlobalDetection: true,
      }),
    ).toBe(false);
  });

  it('shows objects at a camera snapshot even if global gate missed', () => {
    expect(
      shouldShowPlaybackObjects({
        showMetadata: true,
        globalTsLength: 3,
        atCameraDetection: true,
        atGlobalDetection: false,
      }),
    ).toBe(true);
  });

  it('does not skip when there is no next snapshot', () => {
    expect(shouldSkipToDetection(100, null, SKIP_GAP_SEC)).toBe(false);
  });

  it('does not skip when next is behind or equal', () => {
    expect(shouldSkipToDetection(100, 100, SKIP_GAP_SEC)).toBe(false);
    expect(shouldSkipToDetection(100, 99.5, SKIP_GAP_SEC)).toBe(false);
  });
});

describe('hasActiveTrackAt', () => {
  const short = [
    { ts: 100, kind: 'found' as const, object_id: 1 },
    { ts: 102, kind: 'lost' as const, object_id: 1 },
  ];

  it('is true between found and lost on a short track', () => {
    expect(hasActiveTrackAt(short, 101)).toBe(true);
  });

  it('is false after lost', () => {
    expect(hasActiveTrackAt(short, 103)).toBe(false);
  });

  it('is true on found and lost snapshots', () => {
    expect(hasActiveTrackAt(short, 100)).toBe(true);
    expect(hasActiveTrackAt(short, 102)).toBe(true);
  });

  it('does not stick for found without lost', () => {
    const unpaired = [{ ts: 100, kind: 'found' as const, object_id: 2 }];
    expect(hasActiveTrackAt(unpaired, 100)).toBe(true);
    expect(hasActiveTrackAt(unpaired, 105)).toBe(false);
  });

  it('does not interpolate a long found-to-lost span', () => {
    const long = [
      { ts: 100, kind: 'found' as const, object_id: 3 },
      { ts: 229, kind: 'lost' as const, object_id: 3 },
    ];
    expect(hasActiveTrackAt(long, 160)).toBe(false);
    expect(hasActiveTrackAt(long, 100)).toBe(true);
    expect(hasActiveTrackAt(long, 229)).toBe(true);
  });
});

describe('objectsToOverlayFromIndex', () => {
  it('builds a normalized box from a snapshot', () => {
    const items = [
      {
        ts: 100,
        kind: 'found' as const,
        object_id: 7,
        class_name: 'person',
        bounding_box: { x: 10, y: 20, width: 30, height: 40 },
      },
    ];
    const objs = objectsToOverlayFromIndex(items, 100, { w: 100, h: 100 });
    expect(objs).toHaveLength(1);
    expect(objs[0].bbox).toEqual([0.1, 0.2, 0.4, 0.6]);
    expect(objs[0].class_name).toBe('person');
  });

  it('lerps bbox on a short track', () => {
    const items = [
      {
        ts: 100,
        kind: 'found' as const,
        object_id: 1,
        bounding_box: { x: 0, y: 0, width: 10, height: 10 },
      },
      {
        ts: 102,
        kind: 'lost' as const,
        object_id: 1,
        bounding_box: { x: 10, y: 0, width: 10, height: 10 },
      },
    ];
    const objs = objectsToOverlayFromIndex(items, 101, { w: 100, h: 100 });
    expect(objs).toHaveLength(1);
    expect(objs[0].bbox?.[0]).toBeCloseTo(0.05, 5);
  });

  it('does not lerp a long found-to-lost span', () => {
    const items = [
      {
        ts: 100,
        kind: 'found' as const,
        object_id: 1,
        bounding_box: { x: 0, y: 0, width: 10, height: 10 },
      },
      {
        ts: 229,
        kind: 'lost' as const,
        object_id: 1,
        bounding_box: { x: 10, y: 0, width: 10, height: 10 },
      },
    ];
    expect(objectsToOverlayFromIndex(items, 160, { w: 100, h: 100 })).toHaveLength(0);
    expect(objectsToOverlayFromIndex(items, 100, { w: 100, h: 100 })).toHaveLength(1);
  });
});

describe('bboxFromIndexBox', () => {
  it('passes through already-normalized xyxy', () => {
    expect(bboxFromIndexBox([0.1, 0.2, 0.3, 0.4])).toEqual([0.1, 0.2, 0.3, 0.4]);
  });
});
