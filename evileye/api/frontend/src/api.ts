/**
 * Frontend API client — полное соответствие эндпоинтам бэкенда.
 * Каждый метод вызывает ровно один HTTP-эндпоинт.
 */
const API_BASE = '/api/v1';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

// ─── System (корневые эндпоинты приложения) ───────────────────────────

export const systemApi = {
  /** GET /ready */
  ready(): Promise<{ status: string }> {
    return fetch('/ready').then((r) => r.json());
  },

  /** GET /api/v1/version */
  version(): Promise<{ evileye: string; api: string }> {
    return request<{ evileye: string; api: string }>('/version');
  },
};

// ─── Configs: файлы конфигурации (CRUD) ───────────────────────────────

/** GET /api/v1/configs — список имён конфигов */
export function configsList(): Promise<string[]> {
  return request<string[]>('/configs');
}

/** GET /api/v1/configs/{name} — тело конфига */
export function configGet(name: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/configs/${encodeURIComponent(name)}`);
}

/** POST /api/v1/configs — создание (body: name, body) */
export function configCreate(name: string, body: Record<string, unknown>): Promise<{ name: string; status: string }> {
  return request<{ name: string; status: string }>('/configs', {
    method: 'POST',
    body: JSON.stringify({ name, body }),
  });
}

/** PUT /api/v1/configs/{name} — обновление (body: body) */
export function configUpdate(name: string, body: Record<string, unknown>): Promise<{ name: string; status: string }> {
  return request<{ name: string; status: string }>(`/configs/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify({ body }),
  });
}

/** DELETE /api/v1/configs/{name} — удаление */
export function configDelete(name: string): Promise<{ name: string; status: string }> {
  return request<{ name: string; status: string }>(`/configs/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  });
}

// ─── Runs: пайплайны (config runs) ──────────────────────────────────────

export interface ConfigRun {
  id: number;
  name: string | null;
  config_path: string;
  pid: number | null;
  state: string;
  error: string | null;
}

/** GET /api/v1/configs/runs — список всех runs */
export function runsList(): Promise<Record<number, ConfigRun>> {
  return request<Record<number, ConfigRun>>('/configs/runs');
}

/** GET /api/v1/configs/runs/{rid} — один run по id */
export function runGet(rid: number): Promise<ConfigRun> {
  return request<ConfigRun>(`/configs/runs/${rid}`);
}

/** POST /api/v1/configs/runs — создание run (body: name?, config_name?, config_body?) */
export function runCreate(payload: {
  name?: string;
  config_name?: string;
  config_body?: Record<string, unknown>;
}): Promise<ConfigRun> {
  return request<ConfigRun>('/configs/runs', { method: 'POST', body: JSON.stringify(payload) });
}

/** POST /api/v1/configs/runs/{rid}/start */
export function runStart(rid: number): Promise<ConfigRun> {
  return request<ConfigRun>(`/configs/runs/${rid}/start`, { method: 'POST' });
}

/** POST /api/v1/configs/runs/{rid}/stop */
export function runStop(rid: number): Promise<ConfigRun> {
  return request<ConfigRun>(`/configs/runs/${rid}/stop`, { method: 'POST' });
}

/** DELETE /api/v1/configs/runs/{rid} */
export function runDelete(rid: number): Promise<{ id: number; status: string }> {
  return request<{ id: number; status: string }>(`/configs/runs/${rid}`, { method: 'DELETE' });
}

// ─── Streaming: стрим и снапшоты пайплайна ─────────────────────────────

/** GET /api/v1/pipelines/{rid}/snapshot — URL для одного кадра (image/jpeg) */
export function streamSnapshotUrl(rid: number): string {
  return `${API_BASE}/pipelines/${rid}/snapshot`;
}

/** GET /api/v1/pipelines/{rid}/stream.mjpg?fps= — URL MJPEG-потока */
export function streamMjpgUrl(rid: number, fps?: number): string {
  const u = `${API_BASE}/pipelines/${rid}/stream.mjpg`;
  return fps != null ? `${u}?fps=${fps}` : u;
}

/** GET /api/v1/pipelines/{rid}/stream:status */
export function streamStatus(rid: number): Promise<{ pipeline_id: number; stream_active: boolean }> {
  return request<{ pipeline_id: number; stream_active: boolean }>(`/pipelines/${rid}/stream:status`);
}

/** POST /api/v1/pipelines/{rid}/stream:stop */
export function streamStop(rid: number): Promise<{ pipeline_id: number; status: string; message: string }> {
  return request<{ pipeline_id: number; status: string; message: string }>(
    `/pipelines/${rid}/stream:stop`,
    { method: 'POST' }
  );
}
