import { API_BASE, request } from './client';

export function streamSnapshotUrl(rid: number, sourceId?: number | null): string {
  const u = `${API_BASE}/runs/${rid}/snapshot`;
  return sourceId != null ? `${u}?source_id=${sourceId}` : u;
}

export function streamMjpgUrl(rid: number, fps?: number, sourceId?: number | null): string {
  const u = `${API_BASE}/runs/${rid}/stream.mjpg`;
  const params = new URLSearchParams();
  if (fps != null) params.set('fps', String(fps));
  if (sourceId != null) params.set('source_id', String(sourceId));
  const qs = params.toString();
  return qs ? `${u}?${qs}` : u;
}

export function streamStatus(rid: number, sourceId?: number | null) {
  return request<{
    run_id: number;
    pipeline_id: number;
    source_id?: number | null;
    stream_active: boolean;
    has_frame: boolean;
    web_stream_available: boolean;
    frame_dir_configured: boolean;
  }>(`/runs/${rid}/stream:status${sourceId != null ? `?source_id=${sourceId}` : ''}`);
}

export function streamStop(rid: number, sourceId?: number | null) {
  return request(`/runs/${rid}/stream:stop${sourceId != null ? `?source_id=${sourceId}` : ''}`, { method: 'POST' });
}

export function streamMetadataWsUrl(rid: number, sourceId?: number | null): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const qs = sourceId != null ? `?source_id=${sourceId}` : '';
  return `${proto}://${window.location.host}/api/v1/runs/${rid}/ws${qs}`;
}
