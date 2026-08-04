import { API_BASE, request } from './client';
import type { PlaybackCamera, PlaybackEventMarker, PlaybackSegment } from './types';

export const playbackApi = {
  cameras(date?: string): Promise<{ items: PlaybackCamera[] }> {
    const qs = date ? `?date=${encodeURIComponent(date)}` : '';
    return request(`/playback/cameras${qs}`);
  },
  segments(camera: string, from?: number, to?: number): Promise<{ items: PlaybackSegment[] }> {
    const p = new URLSearchParams({ camera });
    if (from != null) p.set('from', String(from));
    if (to != null) p.set('to', String(to));
    return request(`/playback/segments?${p}`);
  },
  events(from?: number, to?: number, camera?: string): Promise<{ items: PlaybackEventMarker[] }> {
    const p = new URLSearchParams();
    if (from != null) p.set('from', String(from));
    if (to != null) p.set('to', String(to));
    if (camera) p.set('camera', camera);
    return request(`/playback/events?${p}`);
  },
  mediaUrl(path: string): string {
    return `${API_BASE}/playback/media?path=${encodeURIComponent(path)}`;
  },
};
