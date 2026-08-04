import { request } from './client';

export const usersApi = {
  list(): Promise<{ items: Array<{ email: string; role: string; status: string; created_at?: number }> }> {
    return request('/users');
  },
  approve(email: string): Promise<{ ok: boolean }> {
    return request(`/users/${encodeURIComponent(email)}/approve`, { method: 'POST' });
  },
  reject(email: string): Promise<{ ok: boolean }> {
    return request(`/users/${encodeURIComponent(email)}/reject`, { method: 'POST' });
  },
};
