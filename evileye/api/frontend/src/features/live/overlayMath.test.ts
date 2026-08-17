import { describe, expect, it } from 'vitest';
import { formatObjectLabel, polygonCentroid, rgbArrayToCss } from './overlayMath';

describe('overlayMath', () => {
  it('formats object label with global id', () => {
    expect(
      formatObjectLabel({
        global_id: 7,
        class_name: 'person',
        track_id: 42,
        conf: 0.913,
      }),
    ).toBe('G7 person [42:0.91]');
  });

  it('computes polygon centroid', () => {
    expect(polygonCentroid([[0, 0], [1, 0], [0, 1]])).toEqual([1 / 3, 1 / 3]);
  });

  it('builds css color from rgb array', () => {
    expect(rgbArrayToCss([255, 0, 0])).toBe('rgb(255, 0, 0)');
  });
});

