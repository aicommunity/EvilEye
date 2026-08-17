import { describe, expect, it } from 'vitest';
import { formatObjectLabel, polygonCentroid, rgbArrayToCss, transformMetadataForCrop } from './overlayMath';

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

  it('transforms metadata into crop space', () => {
    const meta = {
      objects: [{ bbox: [0.5, 0.5, 0.75, 0.75] as [number, number, number, number] }],
      zones: [{ points: [[0.5, 0.5], [0.6, 0.5], [0.6, 0.6]] as [number, number][] }],
    };
    const cropped = transformMetadataForCrop(meta, [960, 540, 960, 540], 1920, 1080);
    expect(cropped?.objects?.[0]?.bbox?.[0]).toBeCloseTo(0, 1);
    expect(cropped?.zones?.[0]?.points?.length).toBeGreaterThan(0);
  });
});
