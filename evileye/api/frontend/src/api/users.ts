import { request } from './client';

export type UserRecord = { email: string; role: string; status: string; created_at?: number };

export const usersApi = {
  list(): Promise<{ items: UserRecord[] }> {
    return request('/users');
  },
  create(body: { email: string; password: string; role?: 'user' | 'admin' }): Promise<{
    ok: boolean;
    user: UserRecord;
    mail?: { sent: boolean; reason?: string };
  }> {
    return request('/users', { method: 'POST', body: JSON.stringify(body) });
  },
  approve(email: string): Promise<{ ok: boolean }> {
    return request(`/users/${encodeURIComponent(email)}/approve`, { method: 'POST' });
  },
  reject(email: string): Promise<{ ok: boolean }> {
    return request(`/users/${encodeURIComponent(email)}/reject`, { method: 'POST' });
  },
};
