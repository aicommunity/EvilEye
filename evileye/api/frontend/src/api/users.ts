import { request } from './client';

export type UserRecord = {
  id: string;
  username: string;
  email: string | null;
  role: string;
  status: string;
  source: 'credentials' | 'store';
  disabled: boolean;
  created_at?: number | null;
  allowed_cameras?: string[];
};

export type PatchUserBody = {
  role?: 'user' | 'admin';
  disabled?: boolean;
  status?: 'pending' | 'approved' | 'rejected' | 'disabled';
  password?: string;
  allowed_cameras?: string[];
};

export type CameraCatalogItem = {
  source_name: string;
  source_id?: number | null;
  source_type?: string | null;
  run_id?: number | null;
};

export const usersApi = {
  list(): Promise<{ items: UserRecord[] }> {
    return request('/users');
  },
  cameraCatalog(): Promise<{ items: CameraCatalogItem[] }> {
    return request('/users/camera-catalog');
  },
  create(body: { email: string; password: string; role?: 'user' | 'admin' }): Promise<{
    ok: boolean;
    user: UserRecord;
    mail?: { sent: boolean; reason?: string };
  }> {
    return request('/users', { method: 'POST', body: JSON.stringify(body) });
  },
  patch(id: string, body: PatchUserBody): Promise<{ ok: boolean; user: UserRecord }> {
    return request(`/users/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) });
  },
  remove(id: string): Promise<{ ok: boolean }> {
    return request(`/users/${encodeURIComponent(id)}`, { method: 'DELETE' });
  },
  approve(email: string): Promise<{ ok: boolean }> {
    return request(`/users/${encodeURIComponent(email)}/approve`, { method: 'POST' });
  },
  reject(email: string): Promise<{ ok: boolean }> {
    return request(`/users/${encodeURIComponent(email)}/reject`, { method: 'POST' });
  },
};
