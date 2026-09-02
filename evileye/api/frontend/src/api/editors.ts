import { request } from './client';

export interface RoiPayload {
  rois: number[][];
  display_rois?: number[][];
  rois_pixel?: number[][];
  coord_ref?: { w: number; h: number };
  restart_required?: boolean;
  applied_live?: boolean;
}

export interface RoiUpdatePayload {
  rois: number[][];
  coord_ref?: { w: number; h: number };
}

export interface ZoneItem {
  name?: string;
  type: 'rect' | 'polygon';
  points: [number, number][];
}

export interface ZonesPayload {
  zones: ZoneItem[];
  restart_required?: boolean;
  applied_live?: boolean;
}

export interface SourceSchedule {
  enabled: boolean;
  weekdays: number[];
  periods: [string, string][];
  class_ids: number[];
}

export interface ScheduleAlarmGlobalPayload {
  camera_cooldown_sec: number;
  default_schedule: SourceSchedule;
  restart_required?: boolean;
  applied_live?: boolean;
}

export interface SourceScheduleAlarmPayload {
  schedule: SourceSchedule;
  has_override: boolean;
  restart_required?: boolean;
  applied_live?: boolean;
}

export interface ZoneDetectorParamsPayload {
  event_threshold: number;
  zone_left_threshold: number;
  restart_required?: boolean;
  applied_live?: boolean;
}

export const editorsApi = {
  getRoi(name: string, sourceId: number): Promise<RoiPayload> {
    return request(`/configs/${encodeURIComponent(name)}/sources/${sourceId}/roi`);
  },
  putRoi(
    name: string,
    sourceId: number,
    payload: RoiUpdatePayload,
  ): Promise<RoiPayload & { status: string }> {
    return request(`/configs/${encodeURIComponent(name)}/sources/${sourceId}/roi`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  },
  getZones(name: string, sourceId: number): Promise<ZonesPayload> {
    return request(`/configs/${encodeURIComponent(name)}/sources/${sourceId}/zones`);
  },
  putZones(name: string, sourceId: number, zones: ZoneItem[]): Promise<ZonesPayload & { status: string }> {
    return request(`/configs/${encodeURIComponent(name)}/sources/${sourceId}/zones`, {
      method: 'PUT',
      body: JSON.stringify({ zones }),
    });
  },
  getZoneDetectorParams(name: string): Promise<ZoneDetectorParamsPayload> {
    return request(`/configs/${encodeURIComponent(name)}/zone-detector-params`);
  },
  putZoneDetectorParams(
    name: string,
    params: Pick<ZoneDetectorParamsPayload, 'event_threshold' | 'zone_left_threshold'>,
  ): Promise<ZoneDetectorParamsPayload & { status: string }> {
    return request(`/configs/${encodeURIComponent(name)}/zone-detector-params`, {
      method: 'PUT',
      body: JSON.stringify(params),
    });
  },
  getClassMapping(name: string): Promise<{ mapping: Record<string, string> }> {
    return request(`/configs/${encodeURIComponent(name)}/class-mapping`);
  },
  putClassMapping(name: string, mapping: Record<string, string>): Promise<{ status: string; restart_required: boolean }> {
    return request(`/configs/${encodeURIComponent(name)}/class-mapping`, {
      method: 'PUT',
      body: JSON.stringify({ mapping }),
    });
  },
  getScheduleAlarm(name: string): Promise<ScheduleAlarmGlobalPayload> {
    return request(`/configs/${encodeURIComponent(name)}/schedule-alarm`);
  },
  putScheduleAlarm(
    name: string,
    body: Pick<ScheduleAlarmGlobalPayload, 'camera_cooldown_sec' | 'default_schedule'>,
  ): Promise<ScheduleAlarmGlobalPayload & { status: string }> {
    return request(`/configs/${encodeURIComponent(name)}/schedule-alarm`, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
  },
  getSourceScheduleAlarm(name: string, sourceId: number): Promise<SourceScheduleAlarmPayload> {
    return request(`/configs/${encodeURIComponent(name)}/sources/${sourceId}/schedule-alarm`);
  },
  putSourceScheduleAlarm(
    name: string,
    sourceId: number,
    schedule: SourceSchedule | null,
  ): Promise<SourceScheduleAlarmPayload & { status: string }> {
    return request(`/configs/${encodeURIComponent(name)}/sources/${sourceId}/schedule-alarm`, {
      method: 'PUT',
      body: JSON.stringify({ schedule }),
    });
  },
};
