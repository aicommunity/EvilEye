import { request } from './client';

export type BanRecord = {
  id?: string;
  ip: string;
  reason?: string;
  source?: string;
  created_at?: number;
  expires_at?: number | null;
  created_by?: string;
  hit_count?: number;
  notes?: string;
};

export const bansApi = {
  list(includeExpired = false): Promise<{ items: BanRecord[] }> {
    const q = includeExpired ? '?include_expired=true' : '';
    return request(`/bans${q}`);
  },
  create(body: {
    ip: string;
    reason?: string;
    notes?: string;
    duration_sec?: number | null;
    expires_at?: number | null;
  }): Promise<{ ok: boolean; ban: BanRecord }> {
    return request('/bans', { method: 'POST', body: JSON.stringify(body) });
  },
  remove(ip: string): Promise<{ ok: boolean }> {
    return request(`/bans/${encodeURIComponent(ip)}`, { method: 'DELETE' });
  },
  prune(): Promise<{ ok: boolean; removed: number }> {
    return request('/bans/prune', { method: 'POST', body: '{}' });
  },
  protection(): Promise<{ protection: Record<string, unknown> }> {
    return request('/bans/protection');
  },
};
