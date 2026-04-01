/**
 * Frontend API client — полное соответствие эндпоинтам бэкенда.
 * Каждый метод вызывает ровно один HTTP-эндпоинт.
 */
const API_BASE = '/api/v1';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'same-origin',
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, (err as { detail?: string }).detail ?? res.statusText);
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

export const authApi = {
  me(): Promise<{ authenticated: boolean; auth_enabled: boolean; user: { username: string; role: string } | null; permissions: string[] }> {
    return request('/auth/me');
  },

  login(username: string, password: string): Promise<{ authenticated: boolean; auth_enabled: boolean; user: { username: string; role: string } | null; permissions: string[] }> {
    return request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  },

  logout(): Promise<{ ok: boolean }> {
    return request('/auth/logout', { method: 'POST' });
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
  managed?: boolean;
  source?: string;
  alive?: boolean;
  frame_dir?: string | null;
}

export interface StateRun extends ConfigRun {
  started_at?: number | null;
  updated_at?: number | null;
  latest_frame_available?: boolean;
  pipeline_class?: string | null;
  detector_count?: number;
  tracker_count?: number;
  event_detector_names?: string[];
  database_enabled?: boolean;
  sources?: Array<{
    source_id: number | null;
    source_name: string;
    source_type?: string | null;
    address?: string | null;
  }>;
  runtime_snapshot?: Record<string, unknown> | null;
}

export interface StateCamera {
  run_id: number;
  run_name: string | null;
  run_state: string;
  pipeline_class?: string | null;
  source_id: number | null;
  source_name: string;
  source_type?: string | null;
  address?: string | null;
  preview_available: boolean;
  alive: boolean;
}

export interface JournalPage<T> {
  available: boolean;
  items: T[];
  total: number;
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

export const stateApi = {
  overview(): Promise<{
    timestamp: number;
    server: {
      status: string;
      current_run_id: number | null;
      current_run_state: string;
      history_runs_total: number;
      cameras_total: number;
      web_previews_available: number;
      log_files: string[];
    };
    current_run: StateRun | null;
    cameras: StateCamera[];
    history_runs: StateRun[];
    latest_logs: Array<{ name: string; updated_at: number; tail: string[] }>;
  }> {
    return request('/state/overview');
  },

  runs(scope: 'current' | 'history' | 'all' = 'current'): Promise<{ current_run: StateRun | null; items: StateRun[] }> {
    return request(`/state/runs?scope=${scope}`);
  },

  run(rid: number): Promise<StateRun> {
    return request(`/state/runs/${rid}`);
  },

  cameras(scope: 'current' | 'all' = 'current'): Promise<{ items: StateCamera[] }> {
    return request(`/state/cameras?scope=${scope}`);
  },
};

export const journalsApi = {
  events(page = 0, size = 30): Promise<JournalPage<Record<string, unknown>>> {
    return request(`/journals/events?page=${page}&size=${size}`);
  },

  objects(page = 0, size = 30): Promise<JournalPage<Record<string, unknown>>> {
    return request(`/journals/objects?page=${page}&size=${size}`);
  },

  configHistory(limit = 30): Promise<{ available: boolean; items: Record<string, unknown>[] }> {
    return request(`/journals/config-history?limit=${limit}`);
  },
};

export const logsApi = {
  runtime(lines = 80, limit = 5): Promise<{ available: boolean; files: Array<{ name: string; updated_at: number; lines: string[] }> }> {
    return request(`/logs?lines=${lines}&limit=${limit}`);
  },
};

// ─── Streaming: стрим и снапшоты runtime-запуска ──────────────────────

/** GET /api/v1/runs/{rid}/snapshot — URL для одного кадра (image/jpeg) */
export function streamSnapshotUrl(rid: number, sourceId?: number | null): string {
  const u = `${API_BASE}/runs/${rid}/snapshot`;
  return sourceId != null ? `${u}?source_id=${sourceId}` : u;
}

/** GET /api/v1/runs/{rid}/stream.mjpg?fps= — URL MJPEG-потока */
export function streamMjpgUrl(rid: number, fps?: number, sourceId?: number | null): string {
  const u = `${API_BASE}/runs/${rid}/stream.mjpg`;
  const params = new URLSearchParams();
  if (fps != null) params.set('fps', String(fps));
  if (sourceId != null) params.set('source_id', String(sourceId));
  const qs = params.toString();
  return qs ? `${u}?${qs}` : u;
}

/** GET /api/v1/runs/{rid}/stream:status */
export function streamStatus(rid: number, sourceId?: number | null): Promise<{
  run_id: number;
  pipeline_id: number;
  source_id?: number | null;
  stream_active: boolean;
  has_frame: boolean;
  web_stream_available: boolean;
  frame_dir_configured: boolean;
}> {
  return request<{
    run_id: number;
    pipeline_id: number;
    stream_active: boolean;
    has_frame: boolean;
    web_stream_available: boolean;
    frame_dir_configured: boolean;
  }>(`/runs/${rid}/stream:status${sourceId != null ? `?source_id=${sourceId}` : ''}`);
}

/** POST /api/v1/runs/{rid}/stream:stop */
export function streamStop(rid: number): Promise<{ run_id: number; pipeline_id: number; status: string; message: string }> {
  return request<{ run_id: number; pipeline_id: number; status: string; message: string }>(
    `/runs/${rid}/stream:stop`,
    { method: 'POST' }
  );
}
