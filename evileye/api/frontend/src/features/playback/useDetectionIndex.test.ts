import { describe, expect, it } from 'vitest';
import { mergeDetectionItems } from './useDetectionIndex';
import type { PlaybackDetectionItem } from '../../api';

describe('mergeDetectionItems', () => {
  it('merges tick rows by ts/kind/object_id without duplicates', () => {
    const a: PlaybackDetectionItem = { ts: 10, kind: 'found', object_id: 1 };
    const b: PlaybackDetectionItem = { ts: 10, kind: 'found', object_id: 1 };
    const c: PlaybackDetectionItem = { ts: 11, kind: 'lost', object_id: 2 };
    const merged = mergeDetectionItems({ Cam1: [a] }, { Cam1: [b, c] }, ['Cam1']);
    expect(merged.Cam1).toHaveLength(2);
    expect(merged.Cam1[0].ts).toBe(10);
    expect(merged.Cam1[1].ts).toBe(11);
  });
});
