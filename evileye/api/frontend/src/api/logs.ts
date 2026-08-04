import { request } from './client';

export const logsApi = {
  list(limit = 50): Promise<{ available: boolean; files: Array<{ name: string; updated_at: number; size_bytes: number }> }> {
    return request(`/logs?limit=${limit}`);
  },
  read(filename: string, tail?: number): Promise<{ name: string; updated_at: number; size_bytes: number; content: string; lines: string[] }> {
    const qs = tail != null ? `?tail=${tail}` : '';
    return request(`/logs/${encodeURIComponent(filename)}${qs}`);
  },
};
