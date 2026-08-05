import { API_BASE, request } from './client';
import type { JournalFiltersMeta, JournalGroupedRow, JournalPage } from './types';

export type JournalDateFilters = {
  source_name?: string;
  event_type?: string;
  date?: string;
  date_from?: string;
  date_to?: string;
};

function journalQuery(page: number, size: number, filters?: JournalDateFilters) {
  const p = new URLSearchParams({ page: String(page), size: String(size) });
  if (filters?.source_name) p.set('source_name', filters.source_name);
  if (filters?.event_type) p.set('event_type', filters.event_type);
  if (filters?.date) {
    p.set('date', filters.date);
  } else {
    if (filters?.date_from) p.set('date_from', filters.date_from);
    if (filters?.date_to) p.set('date_to', filters.date_to);
  }
  return p.toString();
}

export const journalsApi = {
  filtersMeta(): Promise<JournalFiltersMeta> {
    return request('/journals/filters/meta');
  },
  eventsGrouped(page = 0, size = 30, filters?: JournalDateFilters) {
    return request<JournalPage<JournalGroupedRow>>(`/journals/events/grouped?${journalQuery(page, size, filters)}`);
  },
  objectsGrouped(page = 0, size = 30, filters?: JournalDateFilters) {
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
  stats(filters?: { date?: string; date_from?: string; date_to?: string }) {
    const p = new URLSearchParams();
    if (filters?.date) {
      p.set('date', filters.date);
    } else {
      if (filters?.date_from) p.set('date_from', filters.date_from);
      if (filters?.date_to) p.set('date_to', filters.date_to);
    }
    const qs = p.toString();
    return request<{ available: boolean; events_total?: number; objects_total?: number }>(
      `/journals/stats${qs ? `?${qs}` : ''}`,
    );
  },
  exportUrl(type: 'events' | 'objects', format: 'csv' | 'json', filters?: JournalDateFilters) {
    const p = new URLSearchParams({ type, format });
    if (filters?.source_name) p.set('source_name', filters.source_name);
    if (filters?.event_type) p.set('event_type', filters.event_type);
    if (filters?.date) {
      p.set('date', filters.date);
    } else {
      if (filters?.date_from) p.set('date_from', filters.date_from);
      if (filters?.date_to) p.set('date_to', filters.date_to);
    }
    return `${API_BASE}/journals/export?${p}`;
  },
  async exportDownload(
    type: 'events' | 'objects',
    format: 'csv' | 'json',
    filters?: JournalDateFilters,
  ): Promise<{ blob: Blob; truncated: boolean; filename: string }> {
    const full = this.exportUrl(type, format, filters);
    const res = await fetch(full, { credentials: 'same-origin' });
    if (!res.ok) {
      throw new Error(res.statusText || 'Export failed');
    }
    const truncated = res.headers.get('X-Export-Truncated') === '1';
    const blob = await res.blob();
    return { blob, truncated, filename: `${type}.${format}` };
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
