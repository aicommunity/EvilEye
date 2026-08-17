import { describe, expect, it } from 'vitest';
import { hasActiveTrackAt, shouldSkipToDetection, shouldShowPlaybackObjects, SKIP_GAP_SEC } from './detectionSync';

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
        atGlobalDetection: false,
      }),
    ).toBe(true);
  });

  it('hides objects when index exists and playhead is off snapshots', () => {
    expect(
      shouldShowPlaybackObjects({
        showMetadata: true,
        globalTsLength: 3,
        atCameraDetection: false,
        atGlobalDetection: false,
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
    expect(shouldSkipToDetection(100, null, 1.0)).toBe(false);
  });

  it('does not skip when next is behind or equal', () => {
    expect(shouldSkipToDetection(100, 100, SKIP_GAP_SEC)).toBe(false);
    expect(shouldSkipToDetection(100, 99.5, SKIP_GAP_SEC)).toBe(false);
  });
});

describe('hasActiveTrackAt', () => {
  const items = [
    { ts: 100, kind: 'found' as const, object_id: 1 },
    { ts: 110, kind: 'lost' as const, object_id: 1 },
  ];

  it('is true between found and lost', () => {
    expect(hasActiveTrackAt(items, 105)).toBe(true);
  });

  it('is false after lost', () => {
    expect(hasActiveTrackAt(items, 111)).toBe(false);
  });

  it('is true on found and lost snapshots', () => {
    expect(hasActiveTrackAt(items, 100)).toBe(true);
    expect(hasActiveTrackAt(items, 110)).toBe(true);
  });

  it('does not stick for found without lost', () => {
    const unpaired = [{ ts: 100, kind: 'found' as const, object_id: 2 }];
    expect(hasActiveTrackAt(unpaired, 100)).toBe(true);
    expect(hasActiveTrackAt(unpaired, 105)).toBe(false);
  });
});
