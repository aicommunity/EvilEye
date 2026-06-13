/**
 * Frontend API client — полное соответствие эндпоинтам бэкенда.
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

export const systemApi = {
  ready(): Promise<{ status: string }> {
    return fetch('/ready').then((r) => r.json());
  },
  version(): Promise<{ evileye: string; api: string }> {
    return request<{ evileye: string; api: string }>('/version');
  },
};

export const authApi = {
  me(): Promise<{ authenticated: boolean; auth_enabled: boolean; user: { username: string; role: string } | null; permissions: string[] }> {
    return request('/auth/me');
  },
  login(username: string, password: string): Promise<{ authenticated: boolean; auth_enabled: boolean; user: { username: string; role: string } | null; permissions: string[] }> {
    return request('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
  },
  register(email: string, password: string): Promise<{ ok: boolean; message: string }> {
    return request('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) });
  },
  logout(): Promise<{ ok: boolean }> {
    return request('/auth/logout', { method: 'POST' });
  },
};

export function configsList(): Promise<string[]> {
  return request<string[]>('/configs');
}

export function configGet(name: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/configs/${encodeURIComponent(name)}`);
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
  uptime_seconds?: number | null;
  latest_frame_available?: boolean;
  pipeline_class?: string | null;
  detector_count?: number;
  tracker_count?: number;
  event_detector_names?: string[];
  database_enabled?: boolean;
  sources?: Array<{ source_id: number | null; source_name: string; source_type?: string | null; address?: string | null }>;
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

export interface JournalGroupedRow {
  time?: string;
  time_lost?: string;
  event?: string;
  information?: string;
  source?: string;
  date_folder?: string;
  preview?: string;
  lost_preview?: string;
  has_found_preview?: boolean;
  has_lost_preview?: boolean;
  has_found_video?: boolean;
  has_lost_video?: boolean;
  has_stream_video?: boolean;
  found_video_path?: string | null;
  lost_video_path?: string | null;
  stream_video_path?: string | null;
  bbox_found?: [number, number, number, number] | null;
  bbox_lost?: [number, number, number, number] | null;
  zone_coords?: [number, number][] | null;
  row_key?: string;
  [key: string]: unknown;
}

export interface JournalFiltersMeta {
  dates: string[];
  source_names: string[];
  event_types_events: string[];
  event_types_objects: string[];
}

export interface JournalPage<T> {
  available: boolean;
  items: T[];
  total: number;
  mode?: string;
  reason?: string;
  message?: string;
}

export function runsList(): Promise<Record<number, ConfigRun>> {
  return request<Record<number, ConfigRun>>('/configs/runs');
}

export function runGet(rid: number): Promise<ConfigRun> {
  return request<ConfigRun>(`/configs/runs/${rid}`);
}

export function runCreate(payload: { name?: string; config_name?: string; config_body?: Record<string, unknown> }): Promise<ConfigRun> {
  return request<ConfigRun>('/configs/runs', { method: 'POST', body: JSON.stringify(payload) });
}

export function runStart(rid: number): Promise<ConfigRun> {
  return request<ConfigRun>(`/configs/runs/${rid}/start`, { method: 'POST' });
}

export function runStop(rid: number): Promise<ConfigRun> {
  return request<ConfigRun>(`/configs/runs/${rid}/stop`, { method: 'POST' });
}

export function runDelete(rid: number): Promise<{ id: number; status: string }> {
  return request(`/configs/runs/${rid}`, { method: 'DELETE' });
}

export const stateApi = {
  overview(): Promise<{
    timestamp: number;
    server: {
      status: string;
      current_run_id: number | null;
      current_run_state: string;
      active_runs_total: number;
      cameras_total: number;
      web_previews_available: number;
      log_files: string[];
      journal_stats?: { available: boolean; events_total?: number; objects_total?: number };
    };
    current_run: StateRun | null;
    active_runs: StateRun[];
    cameras: StateCamera[];
    latest_logs: Array<{ name: string; updated_at: number; tail: string[] }>;
  }> {
    return request('/state/overview');
  },
  runs(scope: 'current' | 'active' | 'history' | 'all' = 'current') {
    return request(`/state/runs?scope=${scope}`);
  },
  run(rid: number): Promise<StateRun> {
    return request(`/state/runs/${rid}`);
  },
  cameras(scope: 'current' | 'active' | 'all' = 'current'): Promise<{ items: StateCamera[] }> {
    return request(`/state/cameras?scope=${scope}`);
  },
};

function journalQuery(page: number, size: number, filters?: { source_name?: string; event_type?: string; date?: string }) {
  const p = new URLSearchParams({ page: String(page), size: String(size) });
  if (filters?.source_name) p.set('source_name', filters.source_name);
  if (filters?.event_type) p.set('event_type', filters.event_type);
  if (filters?.date) p.set('date', filters.date);
  return p.toString();
}

export const journalsApi = {
  filtersMeta(): Promise<JournalFiltersMeta> {
    return request<JournalFiltersMeta>('/journals/filters/meta');
  },
  eventsGrouped(page = 0, size = 30, filters?: { source_name?: string; event_type?: string; date?: string }) {
    return request<JournalPage<JournalGroupedRow>>(`/journals/events/grouped?${journalQuery(page, size, filters)}`);
  },
  objectsGrouped(page = 0, size = 30, filters?: { source_name?: string; event_type?: string; date?: string }) {
    return request<JournalPage<JournalGroupedRow>>(`/journals/objects/grouped?${journalQuery(page, size, filters)}`);
  },
  configHistory(limit = 30) {
    return request<{ available: boolean; items: Record<string, unknown>[]; message?: string; reason?: string }>(
      `/journals/config-history?limit=${limit}`,
    );
  },
};

export function journalPreviewUrl(params: {
  path: string;
  date?: string | null;
  journalType: 'events' | 'objects';
  mode?: 'found' | 'lost';
}): string {
  const p = new URLSearchParams({ path: params.path, journal_type: params.journalType });
  if (params.date) p.set('date', params.date);
  if (params.mode) p.set('mode', params.mode);
  return `${API_BASE}/journals/preview?${p}`;
}

export function journalFrameUrl(params: {
  path: string;
  date?: string | null;
  journalType: 'events' | 'objects';
  mode?: 'found' | 'lost';
}): string {
  const p = new URLSearchParams({ path: params.path, journal_type: params.journalType });
  if (params.date) p.set('date', params.date);
  if (params.mode) p.set('mode', params.mode);
  return `${API_BASE}/journals/frame?${p}`;
}

export function journalVideoUrl(params: { path: string }): string {
  const p = new URLSearchParams({ path: params.path });
  return `${API_BASE}/journals/video?${p}`;
}

/** @deprecated use journalPreviewUrl({ path, date, journalType }) */
export function journalPreviewUrlLegacy(path: string, date?: string | null, journalType: 'events' | 'objects' = 'events'): string {
  return journalPreviewUrl({ path, date, journalType });
}

export const logsApi = {
  list(limit = 50): Promise<{ available: boolean; files: Array<{ name: string; updated_at: number; size_bytes: number }> }> {
    return request(`/logs?limit=${limit}`);
  },
  read(filename: string, tail?: number): Promise<{ name: string; updated_at: number; size_bytes: number; content: string; lines: string[] }> {
    const qs = tail != null ? `?tail=${tail}` : '';
    return request(`/logs/${encodeURIComponent(filename)}${qs}`);
  },
};

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

export function streamSnapshotUrl(rid: number, sourceId?: number | null): string {
  const u = `${API_BASE}/runs/${rid}/snapshot`;
  return sourceId != null ? `${u}?source_id=${sourceId}` : u;
}

export function streamMjpgUrl(rid: number, fps?: number, sourceId?: number | null): string {
  const u = `${API_BASE}/runs/${rid}/stream.mjpg`;
  const params = new URLSearchParams();
  if (fps != null) params.set('fps', String(fps));
  if (sourceId != null) params.set('source_id', String(sourceId));
  const qs = params.toString();
  return qs ? `${u}?${qs}` : u;
}

export function streamStatus(rid: number, sourceId?: number | null): Promise<{
  run_id: number;
  pipeline_id: number;
  source_id?: number | null;
  stream_active: boolean;
  has_frame: boolean;
  web_stream_available: boolean;
  frame_dir_configured: boolean;
}> {
  return request(`/runs/${rid}/stream:status${sourceId != null ? `?source_id=${sourceId}` : ''}`);
}

export function streamStop(rid: number, sourceId?: number | null) {
  return request(`/runs/${rid}/stream:stop${sourceId != null ? `?source_id=${sourceId}` : ''}`, { method: 'POST' });
}
