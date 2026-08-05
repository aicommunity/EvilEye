import { request } from './client';
import type { AuthMeResponse } from './types';

export const authApi = {
  me(): Promise<AuthMeResponse> {
    return request('/auth/me');
  },
  login(username: string, password: string): Promise<AuthMeResponse> {
    return request('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
  },
  register(email: string, password: string): Promise<{ ok: boolean; message: string }> {
    return request('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) });
  },
  logout(): Promise<{ ok: boolean }> {
    return request('/auth/logout', { method: 'POST' });
  },
  changePassword(body: { current_password: string; new_password: string }): Promise<{ ok: boolean }> {
    return request('/auth/change-password', { method: 'POST', body: JSON.stringify(body) });
  },
};

export const systemApi = {
  ready(): Promise<{ status: string }> {
    return fetch('/ready').then((r) => r.json());
  },
  version(): Promise<{ evileye: string; api: string }> {
    return request('/version');
  },
};
