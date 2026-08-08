import { request } from './client';

export interface RoiPayload {
  rois: number[][];
  restart_required?: boolean;
}

export interface ZoneItem {
  name?: string;
  type: 'rect' | 'polygon';
  points: [number, number][];
}

export interface ZonesPayload {
  zones: ZoneItem[];
  restart_required?: boolean;
}

export const editorsApi = {
  getRoi(name: string, sourceId: number): Promise<RoiPayload> {
    return request(`/configs/${encodeURIComponent(name)}/sources/${sourceId}/roi`);
  },
  putRoi(name: string, sourceId: number, rois: number[][]): Promise<RoiPayload & { status: string }> {
    return request(`/configs/${encodeURIComponent(name)}/sources/${sourceId}/roi`, {
      method: 'PUT',
      body: JSON.stringify({ rois }),
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
  getClassMapping(name: string): Promise<{ mapping: Record<string, string> }> {
    return request(`/configs/${encodeURIComponent(name)}/class-mapping`);
  },
  putClassMapping(name: string, mapping: Record<string, string>): Promise<{ status: string; restart_required: boolean }> {
    return request(`/configs/${encodeURIComponent(name)}/class-mapping`, {
      method: 'PUT',
      body: JSON.stringify({ mapping }),
    });
  },
};
