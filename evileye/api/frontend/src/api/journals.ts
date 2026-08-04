import { API_BASE, request } from './client';
import type { JournalFiltersMeta, JournalGroupedRow, JournalPage } from './types';

function journalQuery(page: number, size: number, filters?: { source_name?: string; event_type?: string; date?: string }) {
  const p = new URLSearchParams({ page: String(page), size: String(size) });
  if (filters?.source_name) p.set('source_name', filters.source_name);
  if (filters?.event_type) p.set('event_type', filters.event_type);
  if (filters?.date) p.set('date', filters.date);
  return p.toString();
}

export const journalsApi = {
  filtersMeta(): Promise<JournalFiltersMeta> {
    return request('/journals/filters/meta');
  },
  eventsGrouped(page = 0, size = 30, filters?: { source_name?: string; event_type?: string; date?: string }) {
    return request<JournalPage<JournalGroupedRow>>(`/journals/events/grouped?${journalQuery(page, size, filters)}`);
  },
  objectsGrouped(page = 0, size = 30, filters?: { source_name?: string; event_type?: string; date?: string }) {
    return request<JournalPage<JournalGroupedRow>>(`/journals/objects/grouped?${journalQuery(page, size, filters)}`);
  },
  configHistory(limit = 30) {
    return request<{ available: boolean; items: Record<string, unknown>[]; message?: string; reason?: string }>(
      `/journals/config-history?limit=${limit}`,
    );
  },
  compareHistory(a: number, b: number) {
    return request<Record<string, unknown>>(`/journals/config-history/compare?a=${a}&b=${b}`);
  },
  restoreHistory(jobId: number, targetName: string) {
    return request<Record<string, unknown>>(
      `/journals/config-history/${jobId}/restore?target_name=${encodeURIComponent(targetName)}`,
      { method: 'POST' },
    );
  },
  rowMeta(rowKeyValue: string, journalType: 'events' | 'objects'): Promise<Partial<JournalGroupedRow>> {
    const p = new URLSearchParams({ row_key: rowKeyValue, journal_type: journalType });
    return request(`/journals/row-meta?${p}`);
  },
  stats(date?: string) {
    const p = new URLSearchParams();
    if (date) p.set('date', date);
    const qs = p.toString();
    return request<{ available: boolean; events_total?: number; objects_total?: number }>(
      `/journals/stats${qs ? `?${qs}` : ''}`,
    );
  },
  exportUrl(type: 'events' | 'objects', format: 'csv' | 'json', filters?: { source_name?: string; event_type?: string; date?: string }) {
    const p = new URLSearchParams({ type, format });
    if (filters?.source_name) p.set('source_name', filters.source_name);
    if (filters?.event_type) p.set('event_type', filters.event_type);
    if (filters?.date) p.set('date', filters.date);
    return `${API_BASE}/journals/export?${p}`;
  },
};

export function journalPreviewUrl(params: {
  path: string;
  date?: string | null;
  journalType: 'events' | 'objects';
  mode?: 'found' | 'lost';
  w?: number;
}): string {
  const p = new URLSearchParams({ path: params.path, journal_type: params.journalType });
  if (params.date) p.set('date', params.date);
  if (params.mode) p.set('mode', params.mode);
  if (params.w) p.set('w', String(params.w));
  return `${API_BASE}/journals/preview?${p}`;
}

export function journalFrameUrl(params: {
  path: string;
  date?: string | null;
  journalType: 'events' | 'objects';
  mode?: 'found' | 'lost';
}): string {
  const p = new URLSearchParams({ path: params.path, journal_type: params.journalType });
  if (params.date) p.set('date', params.date);
  if (params.mode) p.set('mode', params.mode);
  return `${API_BASE}/journals/frame?${p}`;
}

export function journalVideoUrl(params: { path: string }): string {
  const p = new URLSearchParams({ path: params.path });
  return `${API_BASE}/journals/video?${p}`;
}
