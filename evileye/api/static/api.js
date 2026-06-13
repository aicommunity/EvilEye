/**
 * Frontend API client — полное соответствие эндпоинтам бэкенда.
 */
const API_BASE = '/api/v1';
export class ApiError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
    }
}
async function request(path, options) {
    const res = await fetch(`${API_BASE}${path}`, {
        credentials: 'same-origin',
        ...options,
        headers: { 'Content-Type': 'application/json', ...options?.headers },
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new ApiError(res.status, err.detail ?? res.statusText);
    }
    return res.json();
}
export const systemApi = {
    ready() {
        return fetch('/ready').then((r) => r.json());
    },
    version() {
        return request('/version');
    },
};
export const authApi = {
    me() {
        return request('/auth/me');
    },
    login(username, password) {
        return request('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
    },
    register(email, password) {
        return request('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) });
    },
    logout() {
        return request('/auth/logout', { method: 'POST' });
    },
};
export function configsList() {
    return request('/configs');
}
export function configGet(name) {
    return request(`/configs/${encodeURIComponent(name)}`);
}
export function configCreate(name, body) {
    return request('/configs', { method: 'POST', body: JSON.stringify({ name, body }) });
}
export function configUpdate(name, body) {
    return request(`/configs/${encodeURIComponent(name)}`, { method: 'PUT', body: JSON.stringify({ body }) });
}
export function configDelete(name) {
    return request(`/configs/${encodeURIComponent(name)}`, { method: 'DELETE' });
}
export function runsList() {
    return request('/configs/runs');
}
export function runGet(rid) {
    return request(`/configs/runs/${rid}`);
}
export function runCreate(payload) {
    return request('/configs/runs', { method: 'POST', body: JSON.stringify(payload) });
}
export function runStart(rid) {
    return request(`/configs/runs/${rid}/start`, { method: 'POST' });
}
export function runStop(rid) {
    return request(`/configs/runs/${rid}/stop`, { method: 'POST' });
}
export function runDelete(rid) {
    return request(`/configs/runs/${rid}`, { method: 'DELETE' });
}
export const stateApi = {
    overview() {
        return request('/state/overview');
    },
    runs(scope = 'current') {
        return request(`/state/runs?scope=${scope}`);
    },
    run(rid) {
        return request(`/state/runs/${rid}`);
    },
    cameras(scope = 'current') {
        return request(`/state/cameras?scope=${scope}`);
    },
};
function journalQuery(page, size, filters) {
    const p = new URLSearchParams({ page: String(page), size: String(size) });
    if (filters?.source_name)
        p.set('source_name', filters.source_name);
    if (filters?.event_type)
        p.set('event_type', filters.event_type);
    if (filters?.date)
        p.set('date', filters.date);
    return p.toString();
}
export const journalsApi = {
    filtersMeta() {
        return request('/journals/filters/meta');
    },
    eventsGrouped(page = 0, size = 30, filters) {
        return request(`/journals/events/grouped?${journalQuery(page, size, filters)}`);
    },
    objectsGrouped(page = 0, size = 30, filters) {
        return request(`/journals/objects/grouped?${journalQuery(page, size, filters)}`);
    },
    configHistory(limit = 30) {
        return request(`/journals/config-history?limit=${limit}`);
    },
};
export function journalPreviewUrl(params) {
    const p = new URLSearchParams({ path: params.path, journal_type: params.journalType });
    if (params.date)
        p.set('date', params.date);
    if (params.mode)
        p.set('mode', params.mode);
    return `${API_BASE}/journals/preview?${p}`;
}
export function journalFrameUrl(params) {
    const p = new URLSearchParams({ path: params.path, journal_type: params.journalType });
    if (params.date)
        p.set('date', params.date);
    if (params.mode)
        p.set('mode', params.mode);
    return `${API_BASE}/journals/frame?${p}`;
}
export function journalVideoUrl(params) {
    const p = new URLSearchParams({ path: params.path });
    return `${API_BASE}/journals/video?${p}`;
}
/** @deprecated use journalPreviewUrl({ path, date, journalType }) */
export function journalPreviewUrlLegacy(path, date, journalType = 'events') {
    return journalPreviewUrl({ path, date, journalType });
}
export const logsApi = {
    list(limit = 50) {
        return request(`/logs?limit=${limit}`);
    },
    read(filename, tail) {
        const qs = tail != null ? `?tail=${tail}` : '';
        return request(`/logs/${encodeURIComponent(filename)}${qs}`);
    },
};
export const usersApi = {
    list() {
        return request('/users');
    },
    approve(email) {
        return request(`/users/${encodeURIComponent(email)}/approve`, { method: 'POST' });
    },
    reject(email) {
        return request(`/users/${encodeURIComponent(email)}/reject`, { method: 'POST' });
    },
};
export function streamSnapshotUrl(rid, sourceId) {
    const u = `${API_BASE}/runs/${rid}/snapshot`;
    return sourceId != null ? `${u}?source_id=${sourceId}` : u;
}
export function streamMjpgUrl(rid, fps, sourceId) {
    const u = `${API_BASE}/runs/${rid}/stream.mjpg`;
    const params = new URLSearchParams();
    if (fps != null)
        params.set('fps', String(fps));
    if (sourceId != null)
        params.set('source_id', String(sourceId));
    const qs = params.toString();
    return qs ? `${u}?${qs}` : u;
}
export function streamStatus(rid, sourceId) {
    return request(`/runs/${rid}/stream:status${sourceId != null ? `?source_id=${sourceId}` : ''}`);
}
export function streamStop(rid, sourceId) {
    return request(`/runs/${rid}/stream:stop${sourceId != null ? `?source_id=${sourceId}` : ''}`, { method: 'POST' });
}
