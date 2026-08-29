import { request } from './client';
import type { AuthMeResponse, UserPrefs } from './types';

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
  changePassword(body: { current_password: string; new_password: string }): Promise<{
    ok: boolean;
    must_change_password?: boolean;
  }> {
    return request('/auth/change-password', { method: 'POST', body: JSON.stringify(body) });
  },
  putPrefs(body: {
    visible_cameras?: string[] | null;
    lang?: 'ru' | 'en';
    date_format?: 'DD-MM-YYYY' | 'YYYY-MM-DD' | 'MM-DD-YYYY';
  }): Promise<{
    ok: boolean;
    prefs: UserPrefs;
    allowed_cameras?: string[];
    camera_access?: 'all' | 'restricted';
  }> {
    return request('/auth/prefs', { method: 'PUT', body: JSON.stringify(body) });
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
