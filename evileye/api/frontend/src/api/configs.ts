import { request } from './client';

export type StudioTab = {
  id: string;
  path: string;
  label_key?: string;
};

export function configsList(): Promise<string[]> {
  return request<string[]>('/configs');
}

export function configGet(name: string): Promise<Record<string, unknown>> {
  return request(`/configs/${encodeURIComponent(name)}`);
}

export function configCreate(name: string, body: Record<string, unknown>): Promise<{ name: string; status: string }> {
  return request('/configs', { method: 'POST', body: JSON.stringify({ name, body }) });
}

export function configUpdate(name: string, body: Record<string, unknown>): Promise<{ name: string; status: string }> {
  return request(`/configs/${encodeURIComponent(name)}`, { method: 'PUT', body: JSON.stringify({ body }) });
}

export function configDelete(name: string): Promise<{ name: string; status: string }> {
  return request(`/configs/${encodeURIComponent(name)}`, { method: 'DELETE' });
}

export function configValidate(name: string): Promise<{ ok: boolean; errors: string[]; warnings: string[] }> {
  return request(`/configs/${encodeURIComponent(name)}/validate`, { method: 'POST' });
}

export function configGetSection(name: string, pathOrKey: string): Promise<unknown> {
  return request(`/configs/${encodeURIComponent(name)}/sections/${encodeURIComponent(pathOrKey)}`);
}

export function configPutSection(
  name: string,
  pathOrKey: string,
  body: unknown,
): Promise<{ name: string; section: string; status: string }> {
  return request(`/configs/${encodeURIComponent(name)}/sections/${encodeURIComponent(pathOrKey)}`, {
    method: 'PUT',
    body: JSON.stringify({ body }),
  });
}

export function configListSections(name: string): Promise<{ sections: string[]; tabs?: StudioTab[] }> {
  return request(`/configs/${encodeURIComponent(name)}/sections`);
}
