import { describe, expect, it } from 'vitest';
import { deriveAlarmCameras } from './alarmCameras';

describe('deriveAlarmCameras', () => {
  it('uses pipeline cameras for split sources when logical_ids missing on basic cards', () => {
    const cameras = deriveAlarmCameras(
      [
        { id: 0, name: 'Cam1', type: 'IpCamera', address: 'rtsp://a' },
        { id: 1, name: 'Cam2', extra_names: ['Cam3'], type: 'IpCamera', address: 'rtsp://b' },
        { id: 3, name: 'Cam4', extra_names: ['Cam5'], type: 'IpCamera', address: 'rtsp://c' },
      ],
      { enabled: false, weekdays: [], periods: [], class_ids: [] },
      null,
      [
        { source_id: 0, source_name: 'Cam1' },
        { source_id: 1, source_name: 'Cam2' },
        { source_id: 2, source_name: 'Cam3' },
        { source_id: 3, source_name: 'Cam4' },
        { source_id: 4, source_name: 'Cam5' },
      ],
    );
    expect(cameras.map((c) => c.name)).toEqual(['Cam1', 'Cam2', 'Cam3', 'Cam4', 'Cam5']);
  });

  it('builds logical cameras from sources when pipeline list missing', () => {
    const cameras = deriveAlarmCameras(
      [
        { id: 0, name: 'Cam1', logical_ids: [0], type: 'IpCamera', address: 'rtsp://a' },
        {
          id: 1,
          name: 'Cam2',
          logical_ids: [1, 2],
          extra_names: ['Cam3'],
          type: 'IpCamera',
          address: 'rtsp://b',
        },
      ],
      { enabled: true, weekdays: [0], periods: [['22:00:00', '06:00:00']], class_ids: [] },
    );
    expect(cameras.map((c) => c.id)).toEqual([0, 1, 2]);
    expect(cameras[2].name).toBe('Cam3');
  });

  it('preserves saved per-camera state', () => {
    const cameras = deriveAlarmCameras(
      [{ id: 0, name: 'Cam1', logical_ids: [0], type: 'IpCamera', address: '' }],
      { enabled: true, weekdays: [], periods: [], class_ids: [] },
      [{ id: 0, name: 'Cam1', alarm_enabled: false }],
      [{ source_id: 0, source_name: 'Cam1' }],
    );
    expect(cameras[0].alarm_enabled).toBe(false);
  });
});
