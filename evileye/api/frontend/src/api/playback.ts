import { API_BASE, request, type RequestOptions } from './client';
import type {
  PlaybackCamera,
  PlaybackDetectionItem,
  PlaybackEventInterval,
  PlaybackEventMarker,
  PlaybackEventsResponse,
  PlaybackSegment,
} from './types';

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
  timeline(
    date: string,
    cameras: string[],
    opts?: RequestOptions & {
      from?: number;
      to?: number;
      runId?: number | null;
      segmentsOnly?: boolean;
    },
  ): Promise<{
    date: string;
    by_camera: Record<
      string,
      {
        segments: PlaybackSegment[];
        detection_ticks: PlaybackDetectionItem[];
        events: PlaybackEventInterval[];
      }
    >;
  }> {
    const p = new URLSearchParams({ date, cameras: cameras.join(',') });
    if (opts?.from != null) p.set('from', String(opts.from));
    if (opts?.to != null) p.set('to', String(opts.to));
    if (opts?.runId != null) p.set('run_id', String(opts.runId));
    if (opts?.segmentsOnly) p.set('segments_only', 'true');
    return request(`/playback/timeline?${p}`, opts);
  },
  events(
    from?: number,
    to?: number,
    camera?: string,
    date?: string,
    cameras?: string[],
    opts?: RequestOptions,
  ): Promise<PlaybackEventsResponse> {
    const p = new URLSearchParams();
    if (from != null) p.set('from', String(from));
    if (to != null) p.set('to', String(to));
    if (camera) p.set('camera', camera);
    if (cameras?.length) p.set('cameras', cameras.join(','));
    if (date) p.set('date', date);
    return request(`/playback/events?${p}`, opts).then((raw: any) => {
      const itemsRaw = Array.isArray(raw?.items) ? raw.items : [];
      const looksLegacy = itemsRaw.length > 0 && itemsRaw[0]?.ts != null && itemsRaw[0]?.start_ts == null;
      if (looksLegacy) {
        return {
          items: [],
          legacy_markers: itemsRaw as PlaybackEventMarker[],
        };
      }
      const items: PlaybackEventInterval[] = itemsRaw
        .map((it: any) => ({
          start_ts: Number(it.start_ts),
          end_ts: Number(it.end_ts),
          event_type: String(it.event_type ?? 'event'),
          label: it.label != null ? String(it.label) : undefined,
          camera: it.camera != null ? String(it.camera) : undefined,
          severity: it.severity ?? undefined,
          zone_id: it.zone_id != null ? String(it.zone_id) : undefined,
          zone_name: it.zone_name != null ? String(it.zone_name) : undefined,
          raw_id: it.raw_id ?? undefined,
        }))
        .filter((it: PlaybackEventInterval) => Number.isFinite(it.start_ts) && Number.isFinite(it.end_ts) && it.end_ts >= it.start_ts);
      const legacy = Array.isArray(raw?.legacy_markers) ? (raw.legacy_markers as PlaybackEventMarker[]) : undefined;
      return { items, legacy_markers: legacy };
    });
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
