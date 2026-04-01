/**
 * Frontend API client — полное соответствие эндпоинтам бэкенда.
 * Каждый метод вызывает ровно один HTTP-эндпоинт.
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
// ─── System (корневые эндпоинты приложения) ───────────────────────────
export const systemApi = {
    /** GET /ready */
    ready() {
        return fetch('/ready').then((r) => r.json());
    },
    /** GET /api/v1/version */
    version() {
        return request('/version');
    },
};
export const authApi = {
    me() {
        return request('/auth/me');
    },
    login(username, password) {
        return request('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });
    },
    logout() {
        return request('/auth/logout', { method: 'POST' });
    },
};
// ─── Configs: файлы конфигурации (CRUD) ───────────────────────────────
/** GET /api/v1/configs — список имён конфигов */
export function configsList() {
    return request('/configs');
}
/** GET /api/v1/configs/{name} — тело конфига */
export function configGet(name) {
    return request(`/configs/${encodeURIComponent(name)}`);
}
/** POST /api/v1/configs — создание (body: name, body) */
export function configCreate(name, body) {
    return request('/configs', {
        method: 'POST',
        body: JSON.stringify({ name, body }),
    });
}
/** PUT /api/v1/configs/{name} — обновление (body: body) */
export function configUpdate(name, body) {
    return request(`/configs/${encodeURIComponent(name)}`, {
        method: 'PUT',
        body: JSON.stringify({ body }),
    });
}
/** DELETE /api/v1/configs/{name} — удаление */
export function configDelete(name) {
    return request(`/configs/${encodeURIComponent(name)}`, {
        method: 'DELETE',
    });
}
/** GET /api/v1/configs/runs — список всех runs */
export function runsList() {
    return request('/configs/runs');
}
/** GET /api/v1/configs/runs/{rid} — один run по id */
export function runGet(rid) {
    return request(`/configs/runs/${rid}`);
}
/** POST /api/v1/configs/runs — создание run (body: name?, config_name?, config_body?) */
export function runCreate(payload) {
    return request('/configs/runs', { method: 'POST', body: JSON.stringify(payload) });
}
/** POST /api/v1/configs/runs/{rid}/start */
export function runStart(rid) {
    return request(`/configs/runs/${rid}/start`, { method: 'POST' });
}
/** POST /api/v1/configs/runs/{rid}/stop */
export function runStop(rid) {
    return request(`/configs/runs/${rid}/stop`, { method: 'POST' });
}
/** DELETE /api/v1/configs/runs/{rid} */
export function runDelete(rid) {
    return request(`/configs/runs/${rid}`, { method: 'DELETE' });
}
// ─── Streaming: стрим и снапшоты пайплайна ─────────────────────────────
/** GET /api/v1/pipelines/{rid}/snapshot — URL для одного кадра (image/jpeg) */
export function streamSnapshotUrl(rid) {
    return `${API_BASE}/pipelines/${rid}/snapshot`;
}
/** GET /api/v1/pipelines/{rid}/stream.mjpg?fps= — URL MJPEG-потока */
export function streamMjpgUrl(rid, fps) {
    const u = `${API_BASE}/pipelines/${rid}/stream.mjpg`;
    return fps != null ? `${u}?fps=${fps}` : u;
}
/** GET /api/v1/pipelines/{rid}/stream:status */
export function streamStatus(rid) {
    return request(`/pipelines/${rid}/stream:status`);
}
/** POST /api/v1/pipelines/{rid}/stream:stop */
export function streamStop(rid) {
    return request(`/pipelines/${rid}/stream:stop`, { method: 'POST' });
}
