import { describe, expect, it } from 'vitest';
import { listCamerasFromConfig } from './cameraList';

describe('listCamerasFromConfig', () => {
  it('parses split source into multiple cameras', () => {
    const config = {
      pipeline: {
        sources: [
          {
            source_ids: [1, 2],
            source_names: ['Cam2', 'Cam3'],
            split: true,
          },
        ],
      },
    };
    expect(listCamerasFromConfig(config)).toEqual([
      { source_id: 1, source_name: 'Cam2' },
      { source_id: 2, source_name: 'Cam3' },
    ]);
  });

  it('returns empty for invalid config', () => {
    expect(listCamerasFromConfig(null)).toEqual([]);
    expect(listCamerasFromConfig({})).toEqual([]);
  });
});
