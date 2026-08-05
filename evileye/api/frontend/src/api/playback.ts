import { API_BASE, request, type RequestOptions } from './client';
import type { PlaybackCamera, PlaybackEventMarker, PlaybackSegment } from './types';

export const playbackApi = {
  cameras(date?: string, runId?: number | null, opts?: RequestOptions): Promise<{ items: PlaybackCamera[] }> {
    const p = new URLSearchParams();
    if (date) p.set('date', date);
    if (runId != null) p.set('run_id', String(runId));
    const qs = p.toString();
    return request(`/playback/cameras${qs ? `?${qs}` : ''}`, opts);
  },
  segments(
    camera: string,
    from?: number,
    to?: number,
    date?: string,
    opts?: RequestOptions,
  ): Promise<{ items: PlaybackSegment[] }> {
    const p = new URLSearchParams({ camera });
    if (from != null) p.set('from', String(from));
    if (to != null) p.set('to', String(to));
    if (date) p.set('date', date);
    return request(`/playback/segments?${p}`, opts);
  },
  segmentsBatch(
    cameras: string[],
    from?: number,
    to?: number,
    date?: string,
    opts?: RequestOptions,
  ): Promise<{ by_camera: Record<string, PlaybackSegment[]>; items: PlaybackSegment[] }> {
    const p = new URLSearchParams({ cameras: cameras.join(',') });
    if (from != null) p.set('from', String(from));
    if (to != null) p.set('to', String(to));
    if (date) p.set('date', date);
    return request(`/playback/segments?${p}`, opts);
  },
  events(
    from?: number,
    to?: number,
    camera?: string,
    date?: string,
    cameras?: string[],
    opts?: RequestOptions,
  ): Promise<{ items: PlaybackEventMarker[] }> {
    const p = new URLSearchParams();
    if (from != null) p.set('from', String(from));
    if (to != null) p.set('to', String(to));
    if (camera) p.set('camera', camera);
    if (cameras?.length) p.set('cameras', cameras.join(','));
    if (date) p.set('date', date);
    return request(`/playback/events?${p}`, opts);
  },
  mediaUrl(path: string): string {
    return `${API_BASE}/playback/media?path=${encodeURIComponent(path)}`;
  },
};
