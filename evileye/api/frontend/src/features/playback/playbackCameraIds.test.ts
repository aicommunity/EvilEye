import { describe, expect, it } from 'vitest';
import {
  filterLogicalCameraIds,
  isCompositeCameraId,
  preferLogicalCameras,
} from './playbackCameraIds';

describe('playbackCameraIds', () => {
  it('detects composite folder ids', () => {
    expect(isCompositeCameraId('Cam2-Cam3')).toBe(true);
    expect(isCompositeCameraId('Cam1')).toBe(false);
  });

  it('filters composite ids from timeline requests', () => {
    expect(filterLogicalCameraIds(['Cam1', 'Cam2-Cam3', 'Cam3', ''])).toEqual(['Cam1', 'Cam3']);
  });

  it('prefers logical cameras in UI lists', () => {
    const cams = [
      { id: 'Cam2-Cam3' },
      { id: 'Cam2' },
      { id: 'Cam3' },
    ];
    expect(preferLogicalCameras(cams).map((c) => c.id)).toEqual(['Cam2', 'Cam3']);
  });
});
