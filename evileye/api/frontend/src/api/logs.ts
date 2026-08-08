import { API_BASE, request, type RequestOptions } from './client';

export const logsApi = {
  list(
    limit = 50,
    opts?: RequestOptions,
  ): Promise<{ available: boolean; files: Array<{ name: string; updated_at: number; size_bytes: number }> }> {
    return request(`/logs?limit=${limit}`, opts);
  },
  read(
    filename: string,
    tail?: number,
    opts?: RequestOptions,
  ): Promise<{ name: string; updated_at: number; size_bytes: number; content: string; lines: string[] }> {
    const qs = tail != null ? `?tail=${tail}` : '';
    return request(`/logs/${encodeURIComponent(filename)}${qs}`, opts);
  },
  streamUrl(filename: string, tail = 200): string {
    return `${API_BASE}/logs/${encodeURIComponent(filename)}/stream?tail=${tail}`;
  },
};
