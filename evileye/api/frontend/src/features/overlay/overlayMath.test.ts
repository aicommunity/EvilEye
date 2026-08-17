import { describe, expect, it } from 'vitest';
import {
  formatObjectLabel,
  polygonCentroid,
  prepareOverlayMetadata,
  rescaleMetadataForVideoSize,
  rgbArrayToCss,
  transformMetadataForCrop,
} from './overlayMath';
import { resolvePlaybackFrameSize } from './playbackFrameSize';

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

  it('rescales metadata when video size differs from coord_ref', () => {
    const meta = {
      coord_ref: { w: 1920, h: 1080 },
      debug_rois: [[0.1, 0.1, 0.2, 0.2] as [number, number, number, number]],
      objects: [{ bbox: [0.5, 0.5, 0.6, 0.6] as [number, number, number, number] }],
    };
    const rescaled = rescaleMetadataForVideoSize(meta, 3840, 2160);
    expect(rescaled?.debug_rois?.[0]?.[0]).toBeCloseTo(0.05, 4);
    expect(rescaled?.objects?.[0]?.bbox?.[0]).toBeCloseTo(0.25, 4);
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

  it('prepareOverlayMetadata is no-op when coord_ref matches display size', () => {
    const meta = {
      coord_ref: { w: 2304, h: 1292 },
      zones: [{ points: [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6], [0.7, 0.8]] as [number, number][] }],
    };
    const prepared = prepareOverlayMetadata(meta, { w: 2304, h: 1292 });
    expect(prepared?.zones?.[0]?.points?.length).toBe(4);
  });

  it('resolvePlaybackFrameSize returns crop dims for split camera', () => {
    const size = resolvePlaybackFrameSize(
      {
        id: 'Cam3',
        name: 'Cam3',
        folder: 'Cam2-Cam3',
        split: true,
        src_coords: [0, 1300, 2304, 1292],
      },
      { w: 2304, h: 2592 },
    );
    expect(size).toEqual({ w: 2304, h: 1292 });
  });
});
