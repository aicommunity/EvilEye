import { API_BASE, request, type RequestOptions } from './client';
import type { PlaybackCamera, PlaybackDetectionItem, PlaybackEventMarker, PlaybackSegment } from './types';

export type FrameSize = { w: number; h: number };

export const PLAYBACK_DETECTION_MATCH_SEC = 0.5;

function appendFrameSize(p: URLSearchParams, frameSize?: FrameSize | null) {
  if (frameSize && frameSize.w > 0 && frameSize.h > 0) {
    p.set('frame_w', String(Math.round(frameSize.w)));
    p.set('frame_h', String(Math.round(frameSize.h)));
  }
}

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
    opts?: RequestOptions & { runId?: number | null },
  ): Promise<{ items: PlaybackSegment[] }> {
    const p = new URLSearchParams({ camera });
    if (from != null) p.set('from', String(from));
    if (to != null) p.set('to', String(to));
    if (date) p.set('date', date);
    if (opts?.runId != null) p.set('run_id', String(opts.runId));
    return request(`/playback/segments?${p}`, opts);
  },
  segmentsBatch(
    cameras: string[],
    from?: number,
    to?: number,
    date?: string,
    opts?: RequestOptions & { runId?: number | null },
  ): Promise<{ by_camera: Record<string, PlaybackSegment[]>; items: PlaybackSegment[] }> {
    const p = new URLSearchParams({ cameras: cameras.join(',') });
    if (from != null) p.set('from', String(from));
    if (to != null) p.set('to', String(to));
    if (date) p.set('date', date);
    if (opts?.runId != null) p.set('run_id', String(opts.runId));
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
  metadata(
    camera: string,
    ts: number,
    date?: string,
    runId?: number | null,
    opts?: RequestOptions & { matchSec?: number; sourceId?: number | null; frameSize?: FrameSize | null },
  ): Promise<{ metadata: import('./types').StreamMetadata }> {
    const p = new URLSearchParams({ camera, ts: String(ts) });
    if (date) p.set('date', date);
    if (runId != null) p.set('run_id', String(runId));
    p.set('window', String(opts?.matchSec ?? PLAYBACK_DETECTION_MATCH_SEC));
    if (opts?.sourceId != null) p.set('source_id', String(opts.sourceId));
    appendFrameSize(p, opts?.frameSize);
    return request(`/playback/metadata?${p}`, opts);
  },
  detections(
    cameras: string[],
    opts?: {
      from?: number;
      to?: number;
      date?: string;
      runId?: number | null;
      ticksOnly?: boolean;
      signal?: AbortSignal;
    },
  ): Promise<{ by_camera: Record<string, PlaybackDetectionItem[]>; items: PlaybackDetectionItem[] }> {
    const p = new URLSearchParams({ cameras: cameras.join(',') });
    if (opts?.from != null) p.set('from', String(opts.from));
    if (opts?.to != null) p.set('to', String(opts.to));
    if (opts?.date) p.set('date', opts.date);
    if (opts?.runId != null) p.set('run_id', String(opts.runId));
    if (opts?.ticksOnly) p.set('ticks_only', '1');
    return request(`/playback/detections?${p}`, { signal: opts?.signal });
  },
  metadataStatic(
    camera: string,
    runId?: number | null,
    opts?: RequestOptions & { sourceId?: number | null; frameSize?: FrameSize | null },
  ): Promise<{ metadata: import('./types').StreamMetadata }> {
    const p = new URLSearchParams({ camera, static_only: 'true' });
    if (runId != null) p.set('run_id', String(runId));
    if (opts?.sourceId != null) p.set('source_id', String(opts.sourceId));
    appendFrameSize(p, opts?.frameSize);
    return request(`/playback/metadata?${p}`, opts);
  },
  metadataBatch(
    cameras: string[],
    ts: number,
    date?: string,
    runId?: number | null,
    opts?: RequestOptions & { window?: number },
  ): Promise<{ by_camera: Record<string, import('./types').StreamMetadata> }> {
    const p = new URLSearchParams({ cameras: cameras.join(','), ts: String(ts) });
    if (date) p.set('date', date);
    if (runId != null) p.set('run_id', String(runId));
    if (opts?.window != null) p.set('window', String(opts.window));
    return request(`/playback/metadata?${p}`, opts);
  },
};
