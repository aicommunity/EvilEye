import { describe, expect, it } from 'vitest';
import { mergeDetectionItems } from './useDetectionIndex';
import type { PlaybackDetectionItem } from '../../api';

describe('mergeDetectionItems', () => {
  it('merges ticks and prefers bounding_box', () => {
    const tick: PlaybackDetectionItem = { ts: 10, kind: 'found', object_id: 1 };
    const full: PlaybackDetectionItem = {
      ts: 10,
      kind: 'found',
      object_id: 1,
      bounding_box: [0, 0, 1, 1],
    };
    const merged = mergeDetectionItems(
      { Cam1: [tick] },
      { Cam1: [full, { ts: 11, kind: 'lost', object_id: 2 }] },
      ['Cam1'],
    );
    expect(merged.Cam1).toHaveLength(2);
    expect(merged.Cam1[0].bounding_box).toEqual([0, 0, 1, 1]);
    expect(merged.Cam1[1].ts).toBe(11);
  });
});
