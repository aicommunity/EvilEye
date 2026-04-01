import { ApiError, authApi, journalsApi, logsApi, stateApi, systemApi, configsList, configGet, configCreate, configUpdate, configDelete, runsList, runGet, runCreate, runStart, runStop, runDelete, streamSnapshotUrl, streamMjpgUrl, streamStop, streamStatus, } from './api.js';
const navOverview = document.getElementById('nav-overview');
const navCameras = document.getElementById('nav-cameras');
const navJournals = document.getElementById('nav-journals');
const navLogs = document.getElementById('nav-logs');
const navConfigs = document.getElementById('nav-configs');
const navRuns = document.getElementById('nav-runs');
const panelOverview = document.getElementById('panel-overview');
const panelCameras = document.getElementById('panel-cameras');
const panelJournals = document.getElementById('panel-journals');
const panelLogs = document.getElementById('panel-logs');
const panelConfigs = document.getElementById('panel-configs');
const panelRuns = document.getElementById('panel-runs');
const overviewRefreshBtn = document.getElementById('overview-refresh-btn');
const overviewCardsEl = document.getElementById('overview-cards');
const overviewRunsEl = document.getElementById('overview-runs');
const camerasRefreshBtn = document.getElementById('cameras-refresh-btn');
const camerasListEl = document.getElementById('cameras-list');
const journalsRefreshBtn = document.getElementById('journals-refresh-btn');
const journalEventsEl = document.getElementById('journal-events');
const journalObjectsEl = document.getElementById('journal-objects');
const journalHistoryEl = document.getElementById('journal-history');
const logsRefreshBtn = document.getElementById('logs-refresh-btn');
const logsListEl = document.getElementById('logs-list');
const configSearchInput = document.getElementById('config-search');
const configsListEl = document.getElementById('configs-list');
const configCreateBtn = document.getElementById('config-create-btn');
const configModal = document.getElementById('config-modal');
const configModalTitle = document.getElementById('config-modal-title');
const configNameInput = document.getElementById('config-name');
const configBodyTextarea = document.getElementById('config-body');
const configSaveBtn = document.getElementById('config-save-btn');
const configModalClose = document.getElementById('config-modal-close');
const configCloseBtn = document.getElementById('config-close-btn');
const runSearchInput = document.getElementById('run-search');
const runsListEl = document.getElementById('runs-list');
const runRefreshBtn = document.getElementById('run-refresh-btn');
const runConfigSelect = document.getElementById('run-config-select');
const runNameInput = document.getElementById('run-name');
const runCreateBtn = document.getElementById('run-create-btn');
const runUseBodyCheck = document.getElementById('run-use-body');
const runBodyWrap = document.getElementById('run-body-wrap');
const runBodyTextarea = document.getElementById('run-body');
const runDetailModal = document.getElementById('run-detail-modal');
const runDetailRid = document.getElementById('run-detail-rid');
const runDetailName = document.getElementById('run-detail-name');
const runDetailState = document.getElementById('run-detail-state');
const runDetailConfigPath = document.getElementById('run-detail-config-path');
const runDetailPid = document.getElementById('run-detail-pid');
const runDetailError = document.getElementById('run-detail-error');
const runDetailActions = document.getElementById('run-detail-actions');
const runDetailClose = document.getElementById('run-detail-close');
const streamContainer = document.getElementById('stream-container');
const streamRidEl = document.getElementById('stream-rid');
const streamNameEl = document.getElementById('stream-name');
const streamStateEl = document.getElementById('stream-state');
const streamStatusEl = document.getElementById('stream-status');
const streamFrame = document.getElementById('stream-frame');
const streamSnapshotImg = document.getElementById('stream-snapshot');
const streamBackBtn = document.getElementById('stream-back-btn');
const streamFpsInput = document.getElementById('stream-fps-input');
const streamApplyFpsBtn = document.getElementById('stream-apply-fps-btn');
const streamSnapshotBtn = document.getElementById('stream-snapshot-btn');
const footerVersion = document.getElementById('footer-version');
const errorToast = document.getElementById('error-toast');
const successToast = document.getElementById('success-toast');
const authStatus = document.getElementById('auth-status');
const authUserLabel = document.getElementById('auth-user-label');
const authLogoutBtn = document.getElementById('auth-logout-btn');
const authModal = document.getElementById('auth-modal');
const authUsernameInput = document.getElementById('auth-username');
const authPasswordInput = document.getElementById('auth-password');
const authLoginBtn = document.getElementById('auth-login-btn');
let currentStreamRid = null;
let currentStreamSourceId = null;
let streamPollTimer = null;
let cameraPreviewTimer = null;
let activePanel = 'overview';
let configEditName = null;
let runsCache = [];
let configNamesCache = [];
let authEnabled = false;
let currentPermissions = new Set();
const stateLabels = {
    created: 'created',
    starting: 'starting',
    running: 'running',
    stopping: 'stopping',
    stopped: 'stopped',
    error: 'error',
};
function showError(msg) {
    errorToast.textContent = msg;
    errorToast.classList.add('show');
    setTimeout(() => errorToast.classList.remove('show'), 4000);
}
function showSuccess(msg) {
    successToast.textContent = msg;
    successToast.classList.add('show');
    setTimeout(() => successToast.classList.remove('show'), 3000);
}
function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}
function hasPermission(permission) {
    return currentPermissions.has(permission) || currentPermissions.has('system:admin');
}
function stateBadge(state) {
    const badgeClass = state === 'running'
        ? 'badge-running'
        : state === 'error'
            ? 'badge-error'
            : state === 'starting'
                ? 'badge-pending'
                : 'badge-stopped';
    return `<span class="badge ${badgeClass}">${escapeHtml(stateLabels[state] ?? state)}</span>`;
}
function streamAvailabilityText(status) {
    if (status.stream_active)
        return 'Viewer active';
    if (status.has_frame)
        return 'Frame ready';
    if (!status.frame_dir_configured)
        return 'No web preview';
    if (!status.web_stream_available)
        return 'Stream unavailable';
    return 'No frame';
}
function openAuthModal() {
    authModal.classList.add('open');
}
function closeAuthModal() {
    authModal.classList.remove('open');
    authPasswordInput.value = '';
}
function updateAuthUi(user) {
    authStatus.classList.toggle('hidden', !authEnabled || user == null);
    authUserLabel.textContent = user ? `${user.username} (${user.role})` : '';
}
function applyAccessPolicy() {
    navJournals.classList.toggle('hidden', !hasPermission('journal:view'));
    navLogs.classList.toggle('hidden', !hasPermission('journal:view'));
    navConfigs.classList.toggle('hidden', !hasPermission('config:view'));
    navRuns.classList.toggle('hidden', !hasPermission('runtime:control'));
    configCreateBtn.classList.toggle('hidden', !hasPermission('config:edit'));
    panelRuns.querySelector('.create-card')?.classList.toggle('hidden', !hasPermission('runtime:control'));
}
function handleApiError(error, fallbackMessage) {
    if (error instanceof ApiError && error.status === 401) {
        openAuthModal();
        showError('Требуется авторизация');
        return;
    }
    if (error instanceof ApiError && error.status === 403) {
        showError(error.message);
        return;
    }
    showError(error instanceof Error ? error.message : fallbackMessage);
}
async function loadSystemInfo() {
    try {
        const v = await systemApi.version();
        footerVersion.textContent = `EvilEye ${v.evileye}`;
    }
    catch {
        footerVersion.textContent = '—';
    }
}
async function bootstrapAuth() {
    try {
        const me = await authApi.me();
        authEnabled = me.auth_enabled;
        currentPermissions = new Set(me.permissions ?? []);
        updateAuthUi(me.user);
        applyAccessPolicy();
        if (!me.auth_enabled) {
            closeAuthModal();
            return true;
        }
        if (me.user) {
            closeAuthModal();
            return true;
        }
        openAuthModal();
        return false;
    }
    catch (e) {
        if (e instanceof ApiError && e.status === 401) {
            authEnabled = true;
            currentPermissions = new Set();
            updateAuthUi(null);
            applyAccessPolicy();
            openAuthModal();
            return false;
        }
        handleApiError(e, 'Не удалось проверить авторизацию');
        return false;
    }
}
async function login() {
    const username = authUsernameInput.value.trim();
    const password = authPasswordInput.value;
    if (!username || !password) {
        showError('Введите имя пользователя и пароль');
        return;
    }
    authLoginBtn.setAttribute('disabled', 'true');
    try {
        const result = await authApi.login(username, password);
        authEnabled = result.auth_enabled;
        currentPermissions = new Set(result.permissions ?? []);
        updateAuthUi(result.user);
        applyAccessPolicy();
        closeAuthModal();
        showSuccess('Вход выполнен');
        await refreshAll();
    }
    catch (e) {
        handleApiError(e, 'Не удалось выполнить вход');
    }
    finally {
        authLoginBtn.removeAttribute('disabled');
    }
}
async function logout() {
    try {
        await authApi.logout();
        currentPermissions = new Set();
        updateAuthUi(null);
        applyAccessPolicy();
        openAuthModal();
        showSuccess('Сессия завершена');
    }
    catch (e) {
        handleApiError(e, 'Не удалось завершить сессию');
    }
}
function showPanel(panel) {
    activePanel = panel;
    panelOverview.classList.toggle('active', panel === 'overview');
    panelCameras.classList.toggle('active', panel === 'cameras');
    panelJournals.classList.toggle('active', panel === 'journals');
    panelLogs.classList.toggle('active', panel === 'logs');
    panelConfigs.classList.toggle('active', panel === 'configs');
    panelRuns.classList.toggle('active', panel === 'runs');
    navOverview.classList.toggle('active', panel === 'overview');
    navCameras.classList.toggle('active', panel === 'cameras');
    navJournals.classList.toggle('active', panel === 'journals');
    navLogs.classList.toggle('active', panel === 'logs');
    navConfigs.classList.toggle('active', panel === 'configs');
    navRuns.classList.toggle('active', panel === 'runs');
}
function renderConfigsList(names, searchQuery) {
    const q = searchQuery.trim().toLowerCase();
    const filtered = q ? names.filter((n) => n.toLowerCase().includes(q)) : names;
    configsListEl.innerHTML =
        filtered.length === 0
            ? '<li class="empty">' + (q ? 'Ничего не найдено.' : 'Конфигов пока нет. Создайте первый.') + '</li>'
            : filtered
                .map((n) => `<li class="config-item" data-name="${n.replace(/"/g, '&quot;')}">
                <span class="config-name">${escapeHtml(n)}</span>
                <div class="config-actions">
                  <button type="button" class="btn btn-sm btn-outline config-view" data-name="${n.replace(/"/g, '&quot;')}">Просмотр</button>
                  <button type="button" class="btn btn-sm btn-outline config-edit" data-name="${n.replace(/"/g, '&quot;')}">Изменить</button>
                  <button type="button" class="btn btn-sm btn-danger config-delete" data-name="${n.replace(/"/g, '&quot;')}">Удалить</button>
                </div>
              </li>`)
                .join('');
}
async function loadConfigs() {
    if (!hasPermission('config:view')) {
        configsListEl.innerHTML = '<li class="empty">Доступ к настройкам доступен только администратору.</li>';
        return;
    }
    try {
        const names = await configsList();
        configNamesCache = names;
        renderConfigsList(names, configSearchInput?.value?.trim() ?? '');
        runConfigSelect.innerHTML = names.map((n) => `<option value="${n.replace(/"/g, '&quot;')}">${escapeHtml(n)}</option>`).join('');
    }
    catch (e) {
        handleApiError(e, 'Не удалось загрузить список конфигов');
    }
}
async function openConfigModal(mode, name) {
    configEditName = null;
    configModal.classList.add('open');
    configBodyTextarea.readOnly = mode === 'view';
    configNameInput.readOnly = mode !== 'create';
    configSaveBtn.classList.toggle('hidden', mode === 'view');
    if (mode === 'create') {
        configModalTitle.textContent = 'Новый конфиг';
        configNameInput.value = '';
        configBodyTextarea.value = '{}';
        return;
    }
    if (!name)
        return;
    configModalTitle.textContent = mode === 'edit' ? `Изменить ${name}` : `Просмотр ${name}`;
    configNameInput.value = name;
    configEditName = name;
    try {
        const body = await configGet(name);
        configBodyTextarea.value = JSON.stringify(body, null, 2);
    }
    catch (e) {
        handleApiError(e, 'Не удалось загрузить конфиг');
    }
}
function closeConfigModal() {
    configModal.classList.remove('open');
}
async function saveConfig() {
    if (!hasPermission('config:edit')) {
        showError('Только администратор может менять конфиги');
        return;
    }
    const name = configEditName ?? configNameInput.value.trim();
    if (!name) {
        showError('Введите имя файла');
        return;
    }
    try {
        const body = JSON.parse(configBodyTextarea.value || '{}');
        if (configEditName) {
            await configUpdate(name, body);
            showSuccess('Конфиг обновлён');
        }
        else {
            await configCreate(name, body);
            showSuccess('Конфиг создан');
        }
        closeConfigModal();
        await loadConfigs();
    }
    catch (e) {
        handleApiError(e, 'Не удалось сохранить конфиг');
    }
}
async function deleteConfig(name) {
    if (!hasPermission('config:edit')) {
        showError('Только администратор может менять конфиги');
        return;
    }
    if (!confirm(`Удалить конфиг ${name}?`))
        return;
    try {
        await configDelete(name);
        showSuccess('Конфиг удалён');
        await loadConfigs();
    }
    catch (e) {
        handleApiError(e, 'Не удалось удалить конфиг');
    }
}
function renderRunsList(runs, searchQuery) {
    const q = searchQuery.trim().toLowerCase();
    const filtered = q
        ? runs.filter((r) => String(r.id).includes(q) ||
            (r.name ?? '').toLowerCase().includes(q) ||
            (r.config_path ?? '').toLowerCase().includes(q) ||
            (r.state ?? '').toLowerCase().includes(q))
        : runs;
    runsListEl.innerHTML =
        filtered.length === 0
            ? '<li class="empty">' + (q ? 'Ничего не найдено.' : 'Запусков пока нет. Создайте выше.') + '</li>'
            : filtered
                .map((r) => `
        <li class="run-item" data-rid="${r.id}">
          <div class="run-info">
            <span class="run-name">${escapeHtml(r.name ?? `Запуск ${r.id}`)}</span>
            <span class="run-id">#${r.id}</span>
            ${stateBadge(r.state)}
            ${r.source ? `<span class="run-id">${escapeHtml(r.source)}</span>` : ''}
            <span class="run-config">${escapeHtml(r.config_path)}</span>
            ${r.error ? `<span class="run-error">${escapeHtml(r.error)}</span>` : ''}
          </div>
          <div class="run-actions">
            <button type="button" class="btn btn-sm btn-outline run-detail" data-rid="${r.id}">Просмотр</button>
            ${r.state === 'running'
                ? `<button type="button" class="btn btn-sm btn-danger run-stop" data-rid="${r.id}">Остановить</button>
                   <button type="button" class="btn btn-sm btn-primary run-stream" data-rid="${r.id}">Поток</button>`
                : `<button type="button" class="btn btn-sm btn-success run-start" data-rid="${r.id}">Запустить</button>
                   <button type="button" class="btn btn-sm btn-outline run-delete" data-rid="${r.id}">Удалить</button>`}
          </div>
        </li>`)
                .join('');
}
async function loadRuns() {
    if (!hasPermission('runtime:view')) {
        runsListEl.innerHTML = '<li class="empty">Недостаточно прав для просмотра запусков.</li>';
        return;
    }
    try {
        const map = await runsList();
        runsCache = Object.entries(map)
            .map(([id, r]) => ({ ...r, id: Number(id) }))
            .sort((a, b) => a.id - b.id);
        renderRunsList(runsCache, runSearchInput?.value?.trim() ?? '');
    }
    catch (e) {
        handleApiError(e, 'Не удалось загрузить список запусков');
    }
}
function renderOverview(overview) {
    const currentRun = overview.current_run;
    overviewCardsEl.innerHTML = `
    <div class="metric-card"><span class="metric-label">Статус сервера</span><strong>${escapeHtml(overview.server.status)}</strong></div>
    <div class="metric-card"><span class="metric-label">Текущий запуск</span><strong>${currentRun ? `#${currentRun.id}` : '—'}</strong></div>
    <div class="metric-card"><span class="metric-label">Состояние запуска</span><strong>${escapeHtml(overview.server.current_run_state)}</strong></div>
    <div class="metric-card"><span class="metric-label">Камеры</span><strong>${overview.server.cameras_total}</strong></div>
    <div class="metric-card"><span class="metric-label">Web preview</span><strong>${overview.server.web_previews_available}</strong></div>`;
    overviewRunsEl.innerHTML = currentRun
        ? `<li class="overview-run"><span class="run-name">${escapeHtml(currentRun.name ?? `Запуск ${currentRun.id}`)}</span><span class="run-id">#${currentRun.id}</span>${stateBadge(currentRun.state)}<span class="run-config">${escapeHtml(currentRun.pipeline_class ?? 'pipeline: n/a')}</span>${currentRun.latest_frame_available ? '<span class="badge badge-running">preview</span>' : ''}</li>`
        : '<li class="empty">Текущий runtime-запуск не найден.</li>';
}
function renderCameras(cameras) {
    const ts = Date.now();
    camerasListEl.innerHTML = cameras.length
        ? cameras
            .map((camera) => `<article class="camera-card"><div class="camera-card-head"><span class="run-name">${escapeHtml(camera.source_name)}</span>${stateBadge(camera.run_state)}</div><p class="hint">Run #${camera.run_id} · source #${camera.source_id ?? '—'} · ${escapeHtml(camera.run_name ?? 'без имени')} · ${escapeHtml(camera.pipeline_class ?? 'pipeline n/a')}</p><p class="camera-meta">${escapeHtml(camera.source_type ?? 'source n/a')} · ${escapeHtml(camera.address ?? 'адрес не указан')}</p>${camera.preview_available ? `<img src="${streamSnapshotUrl(camera.run_id, camera.source_id)}&t=${ts}" alt="Preview ${escapeHtml(camera.source_name)}" class="camera-preview" data-rid="${camera.run_id}" data-sid="${camera.source_id ?? ''}">` : `<div class="camera-preview camera-preview-empty">${camera.run_state === 'running' ? 'Кадр ещё не готов' : 'Запуск остановлен'}</div>`}<div class="camera-actions"><button type="button" class="btn btn-sm btn-outline camera-open-stream" data-rid="${camera.run_id}" data-sid="${camera.source_id ?? ''}" ${camera.preview_available ? '' : 'disabled'}>Открыть поток</button></div></article>`)
            .join('')
        : '<p class="empty">Сведения о камерах пока недоступны.</p>';
    camerasListEl.querySelectorAll('.camera-open-stream').forEach((btn) => {
        btn.addEventListener('click', () => openStream(Number(btn.dataset.rid), Number(btn.dataset.sid)));
    });
    camerasListEl.querySelectorAll('.camera-preview[data-rid][data-sid]').forEach((img) => {
        img.addEventListener('error', () => disableCameraPreview(img));
    });
    scheduleCameraPreviewRefresh();
}
function stopCameraPreviewRefresh() {
    if (cameraPreviewTimer != null) {
        window.clearInterval(cameraPreviewTimer);
        cameraPreviewTimer = null;
    }
}
function disableCameraPreview(img) {
    const placeholder = document.createElement('div');
    placeholder.className = 'camera-preview camera-preview-empty';
    placeholder.textContent = 'Preview остановлен';
    const objectUrl = img.dataset.objectUrl;
    if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
    }
    img.replaceWith(placeholder);
    if (!camerasListEl.querySelector('.camera-preview[data-rid][data-sid]')) {
        stopCameraPreviewRefresh();
    }
}
function requestCameraPreview(img, rid, sid) {
    if (img.dataset.previewLoading === '1') {
        img.dataset.previewPending = '1';
        return;
    }
    img.dataset.previewLoading = '1';
    img.dataset.previewPending = '0';
    const url = `${streamSnapshotUrl(rid, sid)}&t=${Date.now()}`;
    void fetch(url, { credentials: 'same-origin', cache: 'no-store' })
        .then((response) => {
        if (!response.ok) {
            throw new Error(`Snapshot request failed: ${response.status}`);
        }
        return response.blob();
    })
        .then((blob) => {
        if (!document.body.contains(img)) {
            return;
        }
        const nextObjectUrl = URL.createObjectURL(blob);
        const previousObjectUrl = img.dataset.objectUrl;
        img.src = nextObjectUrl;
        img.dataset.objectUrl = nextObjectUrl;
        if (previousObjectUrl) {
            URL.revokeObjectURL(previousObjectUrl);
        }
    })
        .catch(() => {
        if (document.body.contains(img)) {
            disableCameraPreview(img);
        }
    })
        .finally(() => {
        img.dataset.previewLoading = '0';
        if (img.dataset.previewPending === '1' && document.body.contains(img)) {
            requestCameraPreview(img, rid, sid);
        }
    });
}
function refreshCameraPreviews() {
    if (activePanel !== 'cameras' || document.visibilityState !== 'visible') {
        return;
    }
    camerasListEl.querySelectorAll('.camera-preview[data-rid][data-sid]').forEach((img) => {
        const rid = Number(img.dataset.rid);
        const sid = Number(img.dataset.sid);
        if (!Number.isNaN(rid) && !Number.isNaN(sid)) {
            const run = runsCache.find((item) => item.id === rid);
            if (run && run.state !== 'running') {
                disableCameraPreview(img);
                return;
            }
            requestCameraPreview(img, rid, sid);
        }
    });
}
function scheduleCameraPreviewRefresh() {
    stopCameraPreviewRefresh();
    if (!camerasListEl.querySelector('.camera-preview[data-rid][data-sid]')) {
        return;
    }
    cameraPreviewTimer = window.setInterval(() => refreshCameraPreviews(), 1500);
}
function renderJournalTable(container, items, columns, emptyText) {
    if (!items.length) {
        container.innerHTML = `<p class="empty">${emptyText}</p>`;
        return;
    }
    const header = columns.map((name) => `<th>${escapeHtml(name)}</th>`).join('');
    const rows = items
        .map((item) => `<tr>${columns.map((column) => `<td>${escapeHtml(String(item[column] ?? '—'))}</td>`).join('')}</tr>`)
        .join('');
    container.innerHTML = `<table class="journal-table"><thead><tr>${header}</tr></thead><tbody>${rows}</tbody></table>`;
}
async function loadOverview() {
    if (!hasPermission('live:view'))
        return;
    renderOverview(await stateApi.overview());
}
async function loadCameras() {
    if (!hasPermission('live:view'))
        return;
    renderCameras((await stateApi.cameras()).items);
}
async function loadJournals() {
    if (!hasPermission('journal:view'))
        return;
    const [events, objects, history] = await Promise.all([
        journalsApi.events(),
        journalsApi.objects(),
        journalsApi.configHistory(),
    ]);
    renderJournalTable(journalEventsEl, events.items, ['event_type', 'source_name', 'information', 'ts'], 'События не найдены.');
    renderJournalTable(journalObjectsEl, objects.items, ['event_type', 'source_name', 'information', 'ts'], 'Объекты не найдены.');
    renderJournalTable(journalHistoryEl, history.items, ['job_id', 'project_id', 'configuration_id', 'status', 'creation_time'], 'История конфигураций недоступна.');
}
async function loadLogs() {
    if (!hasPermission('journal:view'))
        return;
    const logs = await logsApi.runtime();
    logsListEl.innerHTML = logs.files.length
        ? logs.files
            .map((file) => `<article class="log-card"><h3>${escapeHtml(file.name)}</h3><pre>${escapeHtml(file.lines.join('\n'))}</pre></article>`)
            .join('')
        : '<p class="empty">Технические логи недоступны.</p>';
}
async function refreshAll() {
    await loadSystemInfo();
    await loadOverview();
    await loadCameras();
    await loadRuns();
    await loadConfigs();
    await loadJournals();
    await loadLogs();
}
function openRunDetail(rid) {
    runDetailRid.textContent = String(rid);
    runDetailName.textContent = '…';
    runDetailState.textContent = '…';
    runDetailConfigPath.textContent = '…';
    runDetailPid.textContent = '…';
    runDetailError.textContent = '';
    runDetailError.classList.add('hidden');
    runDetailModal.classList.add('open');
    runGet(rid)
        .then((run) => {
        runDetailName.textContent = run.name ?? `Запуск ${rid}`;
        runDetailState.textContent = stateLabels[run.state] ?? run.state;
        runDetailState.className = `badge ${run.state === 'running' ? 'badge-running' : 'badge-stopped'}`;
        runDetailConfigPath.textContent = run.config_path ?? '—';
        runDetailPid.textContent = run.pid != null ? String(run.pid) : '—';
        if (run.error) {
            runDetailError.textContent = run.error;
            runDetailError.classList.remove('hidden');
        }
        runDetailActions.innerHTML =
            run.state === 'running' || run.state === 'starting'
                ? `<button type="button" class="btn btn-sm btn-danger run-detail-stop" data-rid="${rid}">Остановить</button><button type="button" class="btn btn-sm btn-primary run-detail-stream" data-rid="${rid}" ${run.state === 'running' ? '' : 'disabled'}>Поток</button>${run.state !== 'running' ? '<span class="run-error">Поток будет доступен после перехода запуска в running.</span>' : ''}`
                : `<button type="button" class="btn btn-sm btn-success run-detail-start" data-rid="${rid}">Запустить</button><button type="button" class="btn btn-sm btn-outline run-detail-delete" data-rid="${rid}">Удалить</button>`;
        runDetailActions.querySelectorAll('[data-rid]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const r = Number(btn.dataset.rid);
                if (btn.classList.contains('run-detail-start'))
                    void startRun(r);
                else if (btn.classList.contains('run-detail-stop'))
                    void stopRun(r);
                else if (btn.classList.contains('run-detail-delete'))
                    void deleteRun(r);
                else if (btn.classList.contains('run-detail-stream')) {
                    closeRunDetail();
                    openStream(r);
                }
            });
        });
    })
        .catch((e) => handleApiError(e, 'Не удалось загрузить данные запуска'));
}
function closeRunDetail() {
    runDetailModal.classList.remove('open');
}
async function createRun() {
    if (!hasPermission('runtime:control')) {
        showError('Только администратор может создавать запуски');
        return;
    }
    const useBody = runUseBodyCheck.checked;
    const payload = {
        name: runNameInput.value?.trim() || undefined,
    };
    if (useBody) {
        try {
            payload.config_body = JSON.parse(runBodyTextarea.value || '{}');
        }
        catch {
            showError('Неверный JSON в конфигурации');
            return;
        }
    }
    else {
        const configName = runConfigSelect.value?.trim();
        if (!configName) {
            showError('Выберите конфиг или вставьте свой JSON');
            return;
        }
        payload.config_name = configName;
    }
    runCreateBtn.setAttribute('disabled', 'true');
    try {
        await runCreate(payload);
        showSuccess('Запуск создан');
        await refreshAll();
        runNameInput.value = '';
        if (useBody)
            runBodyTextarea.value = '{}';
    }
    catch (e) {
        handleApiError(e, 'Не удалось создать запуск');
    }
    finally {
        runCreateBtn.removeAttribute('disabled');
    }
}
async function startRun(rid) {
    if (!hasPermission('runtime:control')) {
        showError('Только администратор может управлять запусками');
        return;
    }
    try {
        await runStart(rid);
        showSuccess('Запуск стартовал');
        await refreshAll();
    }
    catch (e) {
        handleApiError(e, 'Не удалось запустить');
    }
}
async function stopRun(rid) {
    if (!hasPermission('runtime:control')) {
        showError('Только администратор может управлять запусками');
        return;
    }
    try {
        await runStop(rid);
        if (currentStreamRid === rid)
            closeStream();
        camerasListEl.querySelectorAll(`.camera-preview[data-rid="${rid}"]`).forEach((img) => disableCameraPreview(img));
        showSuccess('Запуск остановлен');
        await refreshAll();
    }
    catch (e) {
        handleApiError(e, 'Не удалось остановить');
    }
}
async function deleteRun(rid) {
    if (!hasPermission('runtime:control')) {
        showError('Только администратор может удалять запуски');
        return;
    }
    if (!confirm(`Удалить запуск ${rid}?`))
        return;
    try {
        await runDelete(rid);
        showSuccess('Запуск удалён');
        closeRunDetail();
        await refreshAll();
        if (currentStreamRid === rid)
            closeStream();
    }
    catch (e) {
        handleApiError(e, 'Не удалось удалить запуск');
    }
}
function openStream(rid, sourceId) {
    const run = runsCache.find((item) => item.id === rid);
    if (run && run.state !== 'running') {
        showError('Поток доступен только для running-запуска.');
        return;
    }
    const fps = streamFpsInput?.value ? Number(streamFpsInput.value) : 10;
    streamFpsInput.value = String(Math.max(1, Math.min(30, fps)));
    currentStreamRid = rid;
    currentStreamSourceId = sourceId ?? null;
    streamRidEl.textContent = String(rid);
    streamNameEl.textContent = '…';
    streamStateEl.textContent = '…';
    streamStatusEl.textContent = '…';
    streamFrame.src = streamMjpgUrl(rid, fps, currentStreamSourceId);
    streamSnapshotImg.src = '';
    streamContainer.classList.add('open');
    streamPollTimer = window.setInterval(() => void pollStreamInfo(), 3000);
    void pollStreamInfo();
}
function applyStreamFps() {
    if (currentStreamRid == null)
        return;
    const fps = streamFpsInput?.value ? Number(streamFpsInput.value) : 10;
    const safeFps = Math.max(1, Math.min(30, fps));
    streamFpsInput.value = String(safeFps);
    streamFrame.src = streamMjpgUrl(currentStreamRid, safeFps, currentStreamSourceId);
    showSuccess(`FPS установлен: ${safeFps}`);
}
function refreshSnapshot() {
    if (currentStreamRid == null)
        return;
    if (streamFrame.src)
        return;
    const base = streamSnapshotUrl(currentStreamRid, currentStreamSourceId);
    streamSnapshotImg.src = `${base}${base.includes('?') ? '&' : '?'}t=${Date.now()}`;
}
async function pollStreamInfo() {
    if (currentStreamRid == null)
        return;
    try {
        const run = await runGet(currentStreamRid);
        if (run.state !== 'running') {
            closeStream();
            return;
        }
        streamNameEl.textContent = run.name ?? `Запуск ${run.id}`;
        streamStateEl.textContent = stateLabels[run.state] ?? run.state;
        streamStateEl.className = `badge ${run.state === 'running' ? 'badge-running' : 'badge-stopped'}`;
        const status = await streamStatus(currentStreamRid, currentStreamSourceId).catch(() => null);
        if (!status) {
            closeStream();
            return;
        }
        if (status) {
            streamStatusEl.textContent = streamAvailabilityText(status);
            streamStatusEl.className = status.stream_active || status.has_frame ? 'stream-status-active' : '';
            if (!status.stream_active && status.has_frame) {
                const base = streamSnapshotUrl(currentStreamRid, currentStreamSourceId);
                streamSnapshotImg.src = `${base}${base.includes('?') ? '&' : '?'}t=${Date.now()}`;
            }
            else if (!status.web_stream_available) {
                streamFrame.src = '';
            }
        }
    }
    catch (e) {
        if (e instanceof ApiError && e.status === 409) {
            showError(e.message);
            closeStream();
        }
    }
}
function closeStream() {
    const rid = currentStreamRid;
    const sourceId = currentStreamSourceId;
    streamFrame.src = '';
    streamSnapshotImg.src = '';
    streamContainer.classList.remove('open');
    currentStreamRid = null;
    currentStreamSourceId = null;
    if (streamPollTimer != null) {
        clearInterval(streamPollTimer);
        streamPollTimer = null;
    }
    if (rid != null) {
        void streamStop(rid, sourceId).catch(() => null);
    }
}
function delegateConfigs(e) {
    const t = e.target.closest('[data-name]');
    if (!t)
        return;
    const name = t.dataset.name;
    if (!name)
        return;
    const target = e.target;
    if (target.classList.contains('config-view'))
        void openConfigModal('view', name);
    else if (target.classList.contains('config-edit'))
        void openConfigModal('edit', name);
    else if (target.classList.contains('config-delete'))
        void deleteConfig(name);
}
function delegateRuns(e) {
    const t = e.target.closest('[data-rid]');
    if (!t)
        return;
    const rid = Number(t.dataset.rid);
    if (Number.isNaN(rid))
        return;
    const target = e.target;
    if (target.classList.contains('run-detail'))
        openRunDetail(rid);
    else if (target.classList.contains('run-start'))
        void startRun(rid);
    else if (target.classList.contains('run-stop'))
        void stopRun(rid);
    else if (target.classList.contains('run-delete'))
        void deleteRun(rid);
    else if (target.classList.contains('run-stream'))
        openStream(rid);
}
export function initDashboard() {
    navOverview.addEventListener('click', () => showPanel('overview'));
    navCameras.addEventListener('click', () => showPanel('cameras'));
    navJournals.addEventListener('click', () => showPanel('journals'));
    navLogs.addEventListener('click', () => showPanel('logs'));
    navConfigs.addEventListener('click', () => showPanel('configs'));
    navRuns.addEventListener('click', () => showPanel('runs'));
    showPanel('overview');
    overviewRefreshBtn.addEventListener('click', () => void refreshAll());
    camerasRefreshBtn.addEventListener('click', () => void loadCameras());
    journalsRefreshBtn.addEventListener('click', () => void loadJournals());
    logsRefreshBtn.addEventListener('click', () => void loadLogs());
    configCreateBtn.addEventListener('click', () => void openConfigModal('create'));
    configModalClose.addEventListener('click', closeConfigModal);
    configModal.querySelector('.modal-backdrop')?.addEventListener('click', closeConfigModal);
    configSaveBtn.addEventListener('click', () => void saveConfig());
    configCloseBtn.addEventListener('click', closeConfigModal);
    configsListEl.addEventListener('click', delegateConfigs);
    configSearchInput?.addEventListener('input', () => renderConfigsList(configNamesCache, configSearchInput.value ?? ''));
    runUseBodyCheck.addEventListener('change', () => {
        runBodyWrap.classList.toggle('hidden', !runUseBodyCheck.checked);
    });
    runCreateBtn.addEventListener('click', () => void createRun());
    runRefreshBtn.addEventListener('click', () => void loadRuns());
    runsListEl.addEventListener('click', delegateRuns);
    runSearchInput?.addEventListener('input', () => renderRunsList(runsCache, runSearchInput.value ?? ''));
    runDetailClose.addEventListener('click', closeRunDetail);
    runDetailModal.querySelector('.modal-backdrop')?.addEventListener('click', closeRunDetail);
    streamBackBtn.addEventListener('click', closeStream);
    streamApplyFpsBtn.addEventListener('click', applyStreamFps);
    streamSnapshotBtn.addEventListener('click', refreshSnapshot);
    authLoginBtn.addEventListener('click', () => void login());
    authLogoutBtn.addEventListener('click', () => void logout());
    authPasswordInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            void login();
        }
    });
    void (async () => {
        const ok = await bootstrapAuth();
        if (!ok)
            return;
        await refreshAll();
    })();
}
initDashboard();
