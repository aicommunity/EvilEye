import { describe, expect, it } from 'vitest';
import { mergePlaybackMetadata } from './mergePlaybackMetadata';

describe('mergePlaybackMetadata', () => {
  it('strips objects when stripObjects is set', () => {
    const out = mergePlaybackMetadata(
      { zones: [{ name: 'Z1', points: [[0, 0], [1, 0], [1, 1]] }] },
      { objects: [{ bbox: [1, 2, 3, 4], class_name: 'person' }] },
      { stripObjects: true },
    );
    expect(out?.objects).toEqual([]);
    expect(out?.zones?.length).toBe(1);
  });

  it('keeps objects in default mode', () => {
    const out = mergePlaybackMetadata(null, {
      objects: [{ bbox: [1, 2, 3, 4] }],
    });
    expect(out?.objects?.length).toBe(1);
  });
});
