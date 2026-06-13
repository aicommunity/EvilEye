import { ApiError, authApi, journalsApi, logsApi, stateApi, systemApi, usersApi, configsList, configGet, configCreate, configUpdate, configDelete, runsList, runGet, runCreate, runStart, runStop, runDelete, streamSnapshotUrl, streamMjpgUrl, streamStop, streamStatus, } from './api.js';
import { isJournalDetailOpen, mergePrependRows, renderJournalTable as renderJournalTableUi, setupJournalInfiniteScroll, } from './journal-ui.js';
const navOverview = document.getElementById('nav-overview');
const navCameras = document.getElementById('nav-cameras');
const navJournals = document.getElementById('nav-journals');
const navLogs = document.getElementById('nav-logs');
const navConfigs = document.getElementById('nav-configs');
const navRuns = document.getElementById('nav-runs');
const navHistory = document.getElementById('nav-history');
const navUsers = document.getElementById('nav-users');
const panelOverview = document.getElementById('panel-overview');
const panelCameras = document.getElementById('panel-cameras');
const panelJournals = document.getElementById('panel-journals');
const panelLogs = document.getElementById('panel-logs');
const panelConfigs = document.getElementById('panel-configs');
const panelRuns = document.getElementById('panel-runs');
const panelHistory = document.getElementById('panel-history');
const panelUsers = document.getElementById('panel-users');
const historyRefreshBtn = document.getElementById('history-refresh-btn');
const historyListEl = document.getElementById('history-list');
const journalFilterDate = document.getElementById('journal-filter-date');
const journalFilterDateAll = document.getElementById('journal-filter-date-all');
const journalFilterEventType = document.getElementById('journal-filter-event-type');
const journalFilterSource = document.getElementById('journal-filter-source');
const journalTabEvents = document.getElementById('journal-tab-events');
const journalTabObjects = document.getElementById('journal-tab-objects');
const journalTabHistory = document.getElementById('journal-tab-history');
const journalPaneEvents = document.getElementById('journal-pane-events');
const journalPaneObjects = document.getElementById('journal-pane-objects');
const journalPaneHistory = document.getElementById('journal-pane-history');
const overviewRefreshBtn = document.getElementById('overview-refresh-btn');
const overviewCardsEl = document.getElementById('overview-cards');
const overviewCurrentRunEl = document.getElementById('overview-current-run');
const overviewCamerasEl = document.getElementById('overview-cameras');
const camerasRefreshBtn = document.getElementById('cameras-refresh-btn');
const camerasListEl = document.getElementById('cameras-list');
const journalsRefreshBtn = document.getElementById('journals-refresh-btn');
const journalEventsEl = document.getElementById('journal-events');
const journalObjectsEl = document.getElementById('journal-objects');
const journalHistoryEl = document.getElementById('journal-history');
const logsRefreshBtn = document.getElementById('logs-refresh-btn');
const logsListEl = document.getElementById('logs-list');
const usersRefreshBtn = document.getElementById('users-refresh-btn');
const usersListEl = document.getElementById('users-list');
const logViewModal = document.getElementById('log-view-modal');
const logViewTitle = document.getElementById('log-view-title');
const logViewContent = document.getElementById('log-view-content');
const logViewDownload = document.getElementById('log-view-download');
const logViewClose = document.getElementById('log-view-close');
const logViewCloseBtn = document.getElementById('log-view-close-btn');
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
const streamBackBtn = document.getElementById('stream-back-btn');
const streamFpsInput = document.getElementById('stream-fps-input');
const streamApplyFpsBtn = document.getElementById('stream-apply-fps-btn');
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
const authRegisterBtn = document.getElementById('auth-register-btn');
const authTabLogin = document.getElementById('auth-tab-login');
const authTabRegister = document.getElementById('auth-tab-register');
const authLoginPanel = document.getElementById('auth-login-panel');
const authRegisterPanel = document.getElementById('auth-register-panel');
const authRegisterEmailInput = document.getElementById('auth-register-email');
const authRegisterPasswordInput = document.getElementById('auth-register-password');
const authRegisterPassword2Input = document.getElementById('auth-register-password2');
let journalEventsPage = 0;
let journalObjectsPage = 0;
let journalRefreshTimer = null;
let journalActiveTab = 'events';
let journalEventsRows = [];
let journalObjectsRows = [];
let journalEventsHasMore = true;
let journalObjectsHasMore = true;
let journalFiltersLoaded = false;
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
function parseOptionalNumber(value) {
    if (value == null || value === '')
        return null;
    const parsed = Number(value);
    return Number.isNaN(parsed) ? null : parsed;
}
function hasPermission(permission) {
    if (!authEnabled)
        return true;
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
function sourceCountLabel(count) {
    if (count % 10 === 1 && count % 100 !== 11)
        return `${count} источник`;
    if (count % 10 >= 2 && count % 10 <= 4 && (count % 100 < 12 || count % 100 > 14))
        return `${count} источника`;
    return `${count} источников`;
}
function formatUptime(startedAt, uptimeSeconds) {
    const sec = uptimeSeconds ?? (startedAt ? Math.floor(Date.now() / 1000 - startedAt) : null);
    if (sec == null || sec < 0)
        return '—';
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    return `${h}ч ${m}м ${s}с`;
}
function formatTimestamp(ts) {
    if (!ts)
        return '—';
    return new Date(ts * 1000).toLocaleString('ru-RU');
}
function formatBytes(size) {
    if (size < 1024)
        return `${size} B`;
    if (size < 1024 * 1024)
        return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}
function renderCameraCard(camera, ts, mini = false) {
    const cardClass = mini ? 'camera-card camera-card-mini' : 'camera-card';
    const canPreview = camera.run_state === 'running';
    const previewReady = camera.preview_available;
    return `<article class="${cardClass}">
    <div class="camera-card-head"><span class="run-name">${escapeHtml(camera.source_name)}</span>${stateBadge(camera.run_state)}</div>
    ${mini ? '' : `<p class="hint">Run #${camera.run_id} · source #${camera.source_id ?? '—'}</p><p class="camera-meta">${escapeHtml(camera.source_type ?? 'source n/a')} · ${escapeHtml(camera.address ?? 'адрес не указан')}</p>`}
    ${canPreview
        ? `<img src="${streamSnapshotUrl(camera.run_id, camera.source_id)}&t=${ts}" alt="Preview ${escapeHtml(camera.source_name)}" class="camera-preview${previewReady ? '' : ' camera-preview-loading'}" data-rid="${camera.run_id}" data-sid="${camera.source_id ?? ''}">`
        : `<div class="camera-preview camera-preview-empty">Запуск остановлен</div>`}
    <div class="camera-actions"><button type="button" class="btn btn-sm btn-outline camera-open-stream" data-rid="${camera.run_id}" data-sid="${camera.source_id ?? ''}" ${canPreview ? '' : 'disabled'}>Открыть поток</button></div>
  </article>`;
}
function bindCameraStreamButtons(container) {
    container.querySelectorAll('.camera-open-stream').forEach((btn) => {
        btn.addEventListener('click', () => openStream(Number(btn.dataset.rid), parseOptionalNumber(btn.dataset.sid)));
    });
    container.querySelectorAll('.camera-preview[data-rid][data-sid]').forEach((img) => {
        img.addEventListener('error', () => disableCameraPreview(img));
    });
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
    navLogs.classList.toggle('hidden', !hasPermission('logs:view'));
    navConfigs.classList.toggle('hidden', !hasPermission('config:view'));
    navRuns.classList.toggle('hidden', !hasPermission('runtime:control'));
    navHistory.classList.toggle('hidden', !hasPermission('history:view'));
    navUsers.classList.toggle('hidden', !hasPermission('users:manage'));
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
async function registerUser() {
    const email = authRegisterEmailInput.value.trim();
    const password = authRegisterPasswordInput.value;
    const password2 = authRegisterPassword2Input.value;
    if (!email || !password) {
        showError('Заполните email и пароль');
        return;
    }
    if (password !== password2) {
        showError('Пароли не совпадают');
        return;
    }
    authRegisterBtn.setAttribute('disabled', 'true');
    try {
        const result = await authApi.register(email, password);
        showSuccess(result.message || 'Регистрация отправлена. Ожидайте подтверждения администратором.');
        authRegisterEmailInput.value = '';
        authRegisterPasswordInput.value = '';
        authRegisterPassword2Input.value = '';
        showAuthTab('login');
    }
    catch (e) {
        handleApiError(e, 'Не удалось зарегистрироваться');
    }
    finally {
        authRegisterBtn.removeAttribute('disabled');
    }
}
function showAuthTab(mode) {
    authLoginPanel.classList.toggle('hidden', mode !== 'login');
    authRegisterPanel.classList.toggle('hidden', mode !== 'register');
    authTabLogin.classList.toggle('btn-primary', mode === 'login');
    authTabLogin.classList.toggle('btn-outline', mode !== 'login');
    authTabRegister.classList.toggle('btn-primary', mode === 'register');
    authTabRegister.classList.toggle('btn-outline', mode !== 'register');
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
    panelHistory.classList.toggle('active', panel === 'history');
    panelUsers.classList.toggle('active', panel === 'users');
    navOverview.classList.toggle('active', panel === 'overview');
    navCameras.classList.toggle('active', panel === 'cameras');
    navJournals.classList.toggle('active', panel === 'journals');
    navLogs.classList.toggle('active', panel === 'logs');
    navConfigs.classList.toggle('active', panel === 'configs');
    navRuns.classList.toggle('active', panel === 'runs');
    navHistory.classList.toggle('active', panel === 'history');
    navUsers.classList.toggle('active', panel === 'users');
    if (panel === 'journals') {
        journalEventsPage = 0;
        journalObjectsPage = 0;
        void ensureJournalFiltersMeta().then(() => loadJournals(false));
        startJournalRefresh();
    }
    else {
        stopJournalRefresh();
    }
    if (panel === 'users')
        void loadUsers();
    if (panel === 'logs')
        void loadLogs();
}
function startJournalRefresh() {
    stopJournalRefresh();
    journalRefreshTimer = window.setInterval(() => {
        if (activePanel !== 'journals' || isJournalDetailOpen())
            return;
        void pollJournals();
    }, 1000);
}
function stopJournalRefresh() {
    if (journalRefreshTimer != null) {
        window.clearInterval(journalRefreshTimer);
        journalRefreshTimer = null;
    }
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
    const stats = overview.server.journal_stats;
    const eventsLabel = stats?.available ? String(stats.events_total ?? 0) : 'БД недоступна';
    const objectsLabel = stats?.available ? String(stats.objects_total ?? 0) : '—';
    overviewCardsEl.innerHTML = `
    <div class="metric-card"><span class="metric-label">Статус сервера</span><strong>${escapeHtml(overview.server.status)}</strong></div>
    <div class="metric-card"><span class="metric-label">Активные запуски</span><strong>${overview.server.active_runs_total}</strong></div>
    <div class="metric-card"><span class="metric-label">Камеры</span><strong>${overview.server.cameras_total}</strong></div>
    <div class="metric-card"><span class="metric-label">Web preview</span><strong>${overview.server.web_previews_available}</strong></div>
    <div class="metric-card"><span class="metric-label">События</span><strong>${escapeHtml(eventsLabel)}</strong></div>
    <div class="metric-card"><span class="metric-label">Объекты</span><strong>${escapeHtml(objectsLabel)}</strong></div>`;
    const run = overview.current_run;
    if (!run) {
        overviewCurrentRunEl.innerHTML = '<p class="empty">Нет активного запуска.</p>';
    }
    else {
        const sourceCount = Array.isArray(run.sources) ? run.sources.length : 0;
        overviewCurrentRunEl.innerHTML = `<div class="overview-run-detail">
      <p><strong>${escapeHtml(run.name ?? `Запуск ${run.id}`)}</strong> #${run.id} ${stateBadge(run.state)}</p>
      <p class="hint">${escapeHtml(run.pipeline_class ?? 'pipeline n/a')} · ${sourceCount > 0 ? sourceCountLabel(sourceCount) : 'Без источников'}</p>
      <p class="hint">Запущен: ${escapeHtml(formatTimestamp(run.started_at ?? null))} · Uptime: ${escapeHtml(formatUptime(run.started_at ?? null, run.uptime_seconds ?? null))}</p>
      <p class="hint">PID: ${run.pid ?? '—'} · ${escapeHtml(run.config_path ?? '—')}</p>
      <button type="button" class="btn btn-sm btn-outline overview-open-detail" data-rid="${run.id}">Подробнее</button>
    </div>`;
        overviewCurrentRunEl.querySelector('.overview-open-detail')?.addEventListener('click', () => openRunDetail(run.id));
    }
    const ts = Date.now();
    const cameras = overview.cameras ?? [];
    overviewCamerasEl.innerHTML = cameras.length
        ? cameras.map((camera) => renderCameraCard(camera, ts, true)).join('')
        : '<p class="empty">Камеры текущего запуска недоступны.</p>';
    bindCameraStreamButtons(overviewCamerasEl);
}
function renderCameras(cameras) {
    const ts = Date.now();
    camerasListEl.innerHTML = cameras.length
        ? `<div class="camera-group-grid">${cameras.map((camera) => renderCameraCard(camera, ts)).join('')}</div>`
        : '<p class="empty">Сведения о камерах текущего запуска пока недоступны.</p>';
    bindCameraStreamButtons(camerasListEl);
    scheduleCameraPreviewRefresh();
}
function stopCameraPreviewRefresh() {
    if (cameraPreviewTimer != null) {
        window.clearInterval(cameraPreviewTimer);
        cameraPreviewTimer = null;
    }
}
function disableCameraPreview(img) {
    const rid = Number(img.dataset.rid);
    const run = runsCache.find((item) => item.id === rid);
    if (run && run.state === 'running') {
        img.classList.add('camera-preview-loading');
        return;
    }
    const placeholder = document.createElement('div');
    placeholder.className = 'camera-preview camera-preview-empty';
    placeholder.textContent = 'Preview остановлен';
    const objectUrl = img.dataset.objectUrl;
    if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
    }
    img.replaceWith(placeholder);
    if (!document.querySelector('.camera-preview[data-rid][data-sid]')) {
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
    const baseUrl = streamSnapshotUrl(rid, sid);
    const url = `${baseUrl}${baseUrl.includes('?') ? '&' : '?'}t=${Date.now()}`;
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
        img.classList.remove('camera-preview-loading');
        if (previousObjectUrl) {
            URL.revokeObjectURL(previousObjectUrl);
        }
    })
        .catch(() => {
        if (document.body.contains(img)) {
            img.classList.add('camera-preview-loading');
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
    if ((activePanel !== 'cameras' && activePanel !== 'overview') || document.visibilityState !== 'visible') {
        return;
    }
    document.querySelectorAll('.camera-preview[data-rid][data-sid]').forEach((img) => {
        const rid = Number(img.dataset.rid);
        const sid = parseOptionalNumber(img.dataset.sid);
        if (!Number.isNaN(rid)) {
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
    if (!document.querySelector('.camera-preview[data-rid][data-sid]')) {
        return;
    }
    cameraPreviewTimer = window.setInterval(() => refreshCameraPreviews(), 1000);
    refreshCameraPreviews();
}
const eventColumns = [
    { key: 'time', label: 'Время' },
    { key: 'event', label: 'Событие' },
    { key: 'information', label: 'Информация' },
    { key: 'source', label: 'Источник' },
    { key: 'time_lost', label: 'Потерян' },
    { key: 'preview', label: 'Preview', preview: true },
];
const objectColumns = [
    { key: 'time', label: 'Время' },
    { key: 'event', label: 'Событие' },
    { key: 'information', label: 'Информация' },
    { key: 'source', label: 'Источник' },
    { key: 'time_lost', label: 'Потерян' },
    { key: 'preview', label: 'Preview', preview: true },
];
async function ensureJournalFiltersMeta() {
    if (journalFiltersLoaded)
        return;
    try {
        const meta = await journalsApi.filtersMeta();
        journalFilterEventType.innerHTML = '<option value="">Все типы</option>';
        const eventTypes = journalActiveTab === 'objects' ? meta.event_types_objects : meta.event_types_events;
        eventTypes.forEach((value) => {
            journalFilterEventType.insertAdjacentHTML('beforeend', `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`);
        });
        journalFilterSource.innerHTML = '<option value="">Все источники</option>';
        meta.source_names.forEach((value) => {
            journalFilterSource.insertAdjacentHTML('beforeend', `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`);
        });
        journalFiltersLoaded = true;
    }
    catch {
        journalFiltersLoaded = true;
    }
}
function setJournalTab(tab) {
    journalActiveTab = tab;
    journalTabEvents.classList.toggle('active', tab === 'events');
    journalTabObjects.classList.toggle('active', tab === 'objects');
    journalTabHistory.classList.toggle('active', tab === 'history');
    journalPaneEvents.classList.toggle('active', tab === 'events');
    journalPaneObjects.classList.toggle('active', tab === 'objects');
    journalPaneHistory.classList.toggle('active', tab === 'history');
    journalFilterSource.classList.toggle('hidden', tab !== 'objects');
    journalFiltersLoaded = false;
    void ensureJournalFiltersMeta();
    if (tab === 'history') {
        void loadJournalHistory();
    }
}
async function loadJournalHistory() {
    if (!hasPermission('history:view')) {
        journalHistoryEl.innerHTML = '<p class="empty">Недостаточно прав для просмотра истории конфигураций.</p>';
        return;
    }
    try {
        const history = await journalsApi.configHistory();
        if (!history.available) {
            const historyMessage = history.message ?? 'История конфигураций недоступна.';
            journalHistoryEl.innerHTML = `<p class="empty">${escapeHtml(String(historyMessage))}</p>`;
            return;
        }
        renderJournalTableUi(journalHistoryEl, history.items, 'events', [
            { key: 'job_id', label: 'Job' },
            { key: 'project_id', label: 'Project' },
            { key: 'configuration_id', label: 'Config' },
            { key: 'status', label: 'Status' },
            { key: 'creation_time', label: 'Created' },
        ], 'История конфигураций пуста.');
    }
    catch (e) {
        handleApiError(e, 'Не удалось загрузить историю конфигураций');
    }
}
async function pollJournals() {
    if (journalActiveTab === 'history')
        return;
    const filters = getJournalFilters();
    try {
        if (journalActiveTab === 'events') {
            const events = await journalsApi.eventsGrouped(0, 30, filters);
            if (!events.available)
                return;
            journalEventsRows = mergePrependRows(journalEventsRows, events.items);
            renderJournalTableUi(journalEventsEl, journalEventsRows, 'events', eventColumns, 'События не найдены.', {
                preserveScroll: true,
            });
        }
        else {
            const objects = await journalsApi.objectsGrouped(0, 30, filters);
            if (!objects.available)
                return;
            journalObjectsRows = mergePrependRows(journalObjectsRows, objects.items);
            renderJournalTableUi(journalObjectsEl, journalObjectsRows, 'objects', objectColumns, 'Объекты не найдены.', {
                preserveScroll: true,
            });
        }
    }
    catch {
        // ignore polling errors
    }
}
async function loadOverview() {
    if (!hasPermission('live:view'))
        return;
    renderOverview(await stateApi.overview());
}
async function loadCameras() {
    if (!hasPermission('live:view'))
        return;
    renderCameras((await stateApi.cameras('current')).items);
}
async function loadJournals(append = false) {
    if (!hasPermission('journal:view'))
        return;
    const filters = getJournalFilters();
    try {
        if (journalActiveTab === 'history') {
            await loadJournalHistory();
            return;
        }
        if (!append) {
            if (journalActiveTab === 'events')
                journalEventsPage = 0;
            else
                journalObjectsPage = 0;
        }
        else if (journalActiveTab === 'events') {
            journalEventsPage += 1;
        }
        else {
            journalObjectsPage += 1;
        }
        if (journalActiveTab === 'events') {
            const events = await journalsApi.eventsGrouped(journalEventsPage, 30, filters);
            if (!events.available) {
                journalEventsEl.innerHTML = `<p class="empty">${escapeHtml(String(events.message ?? 'Журнал событий недоступен.'))}</p>`;
                return;
            }
            journalEventsRows = append ? [...journalEventsRows, ...events.items] : events.items;
            journalEventsHasMore = events.items.length >= 30;
            renderJournalTableUi(journalEventsEl, journalEventsRows, 'events', eventColumns, 'События не найдены.', {
                append,
            });
            return;
        }
        const objects = await journalsApi.objectsGrouped(journalObjectsPage, 30, filters);
        if (!objects.available) {
            journalObjectsEl.innerHTML = `<p class="empty">${escapeHtml(String(objects.message ?? 'Журнал объектов недоступен.'))}</p>`;
            return;
        }
        journalObjectsRows = append ? [...journalObjectsRows, ...objects.items] : objects.items;
        journalObjectsHasMore = objects.items.length >= 30;
        renderJournalTableUi(journalObjectsEl, journalObjectsRows, 'objects', objectColumns, 'Объекты не найдены.', {
            append,
        });
    }
    catch (e) {
        handleApiError(e, 'Не удалось загрузить журналы');
    }
}
async function loadHistory() {
    if (!hasPermission('history:view')) {
        historyListEl.innerHTML = '<p class="empty">Недостаточно прав для просмотра истории.</p>';
        return;
    }
    try {
        const data = (await stateApi.runs('history'));
        const runs = data.items ?? [];
        if (!runs.length) {
            historyListEl.innerHTML = '<p class="empty">Нет записей истории запусков.</p>';
            return;
        }
        const cols = ['id', 'name', 'pipeline_class', 'state', 'pid', 'error'];
        const header = cols.map((c) => `<th>${escapeHtml(c)}</th>`).join('');
        const rows = runs
            .map((r) => {
            const rec = r;
            return `<tr>${cols.map((c) => `<td>${escapeHtml(String(rec[c] ?? '—'))}</td>`).join('')}</tr>`;
        })
            .join('');
        historyListEl.innerHTML = `<table class="journal-table"><thead><tr>${header}</tr></thead><tbody>${rows}</tbody></table>`;
    }
    catch (e) {
        handleApiError(e, 'Не удалось загрузить историю запусков');
    }
}
async function loadLogs() {
    if (!hasPermission('logs:view'))
        return;
    try {
        const logs = await logsApi.list();
        logsListEl.innerHTML = logs.files.length
            ? `<table class="journal-table log-files-table"><thead><tr><th>Файл</th><th>Размер</th><th>Обновлён</th></tr></thead><tbody>${logs.files
                .map((file) => `<tr class="log-file-row" data-name="${escapeHtml(file.name)}"><td>${escapeHtml(file.name)}</td><td>${escapeHtml(formatBytes(file.size_bytes))}</td><td>${escapeHtml(formatTimestamp(file.updated_at))}</td></tr>`)
                .join('')}</tbody></table>`
            : '<p class="empty">Технические логи недоступны.</p>';
        logsListEl.querySelectorAll('.log-file-row').forEach((row) => {
            row.addEventListener('click', () => void openLogFile(row.dataset.name ?? ''));
        });
    }
    catch (e) {
        handleApiError(e, 'Не удалось загрузить список логов');
    }
}
async function openLogFile(name) {
    if (!name)
        return;
    try {
        const payload = await logsApi.read(name);
        logViewTitle.textContent = payload.name;
        logViewContent.textContent = payload.content;
        logViewDownload.href = URL.createObjectURL(new Blob([payload.content], { type: 'text/plain' }));
        logViewDownload.download = payload.name;
        logViewModal.classList.add('open');
    }
    catch (e) {
        handleApiError(e, 'Не удалось открыть лог');
    }
}
function closeLogView() {
    logViewModal.classList.remove('open');
    logViewContent.textContent = '';
    if (logViewDownload.href.startsWith('blob:'))
        URL.revokeObjectURL(logViewDownload.href);
    logViewDownload.removeAttribute('href');
}
async function loadUsers() {
    if (!hasPermission('users:manage'))
        return;
    try {
        const data = await usersApi.list();
        const items = data.items ?? [];
        if (!items.length) {
            usersListEl.innerHTML = '<p class="empty">Пользователей пока нет.</p>';
            return;
        }
        usersListEl.innerHTML = `<table class="journal-table"><thead><tr><th>Email</th><th>Роль</th><th>Статус</th><th>Действия</th></tr></thead><tbody>${items
            .map((user) => `<tr><td>${escapeHtml(user.email)}</td><td>${escapeHtml(user.role ?? 'user')}</td><td>${escapeHtml(user.status ?? '—')}</td><td>${user.status === 'pending'
            ? `<button type="button" class="btn btn-sm btn-success user-approve" data-email="${escapeHtml(user.email)}">Approve</button> <button type="button" class="btn btn-sm btn-danger user-reject" data-email="${escapeHtml(user.email)}">Reject</button>`
            : '—'}</td></tr>`)
            .join('')}</tbody></table>`;
        usersListEl.querySelectorAll('.user-approve').forEach((btn) => {
            btn.addEventListener('click', () => void approveUser(btn.dataset.email ?? ''));
        });
        usersListEl.querySelectorAll('.user-reject').forEach((btn) => {
            btn.addEventListener('click', () => void rejectUser(btn.dataset.email ?? ''));
        });
    }
    catch (e) {
        handleApiError(e, 'Не удалось загрузить пользователей');
    }
}
async function approveUser(email) {
    try {
        await usersApi.approve(email);
        showSuccess(`Пользователь ${email} подтверждён`);
        await loadUsers();
    }
    catch (e) {
        handleApiError(e, 'Не удалось подтвердить пользователя');
    }
}
async function rejectUser(email) {
    try {
        await usersApi.reject(email);
        showSuccess(`Регистрация ${email} отклонена`);
        await loadUsers();
    }
    catch (e) {
        handleApiError(e, 'Не удалось отклонить пользователя');
    }
}
function getJournalFilters() {
    const filters = {};
    const src = journalFilterSource?.value?.trim();
    const evt = journalFilterEventType?.value?.trim();
    const date = journalFilterDate?.value?.trim();
    if (src)
        filters.source_name = src;
    if (evt)
        filters.event_type = evt;
    if (date)
        filters.date = date;
    return filters;
}
async function refreshAll() {
    await loadSystemInfo();
    await loadRuns();
    await loadOverview();
    await loadCameras();
    await loadConfigs();
    if (activePanel === 'journals')
        await loadJournals(false);
    if (hasPermission('logs:view'))
        await loadLogs();
    if (hasPermission('history:view'))
        await loadHistory();
    if (hasPermission('users:manage'))
        await loadUsers();
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
                    showError('Выберите камеру на вкладке «Камеры» для открытия потока.');
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
        streamStatusEl.textContent = streamAvailabilityText(status);
        streamStatusEl.className = status.stream_active || status.has_frame ? 'stream-status-active' : '';
        if (!status.web_stream_available) {
            streamFrame.src = '';
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
    else if (target.classList.contains('run-stream')) {
        showError('Выберите камеру на вкладке «Камеры» для открытия потока.');
    }
}
export function initDashboard() {
    navOverview.addEventListener('click', () => showPanel('overview'));
    navCameras.addEventListener('click', () => showPanel('cameras'));
    navJournals.addEventListener('click', () => showPanel('journals'));
    navLogs.addEventListener('click', () => showPanel('logs'));
    navConfigs.addEventListener('click', () => showPanel('configs'));
    navRuns.addEventListener('click', () => showPanel('runs'));
    navHistory.addEventListener('click', () => showPanel('history'));
    navUsers.addEventListener('click', () => showPanel('users'));
    showPanel('overview');
    overviewRefreshBtn.addEventListener('click', () => void refreshAll());
    camerasRefreshBtn.addEventListener('click', () => void loadCameras());
    journalsRefreshBtn.addEventListener('click', () => void loadJournals(false));
    setupJournalInfiniteScroll(journalEventsEl, async () => {
        if (journalActiveTab !== 'events' || !journalEventsHasMore)
            return;
        await loadJournals(true);
    });
    setupJournalInfiniteScroll(journalObjectsEl, async () => {
        if (journalActiveTab !== 'objects' || !journalObjectsHasMore)
            return;
        await loadJournals(true);
    });
    logsRefreshBtn.addEventListener('click', () => void loadLogs());
    usersRefreshBtn.addEventListener('click', () => void loadUsers());
    historyRefreshBtn.addEventListener('click', () => void loadHistory());
    journalTabEvents.addEventListener('click', () => {
        setJournalTab('events');
        void loadJournals(false);
    });
    journalTabObjects.addEventListener('click', () => {
        setJournalTab('objects');
        void loadJournals(false);
    });
    journalTabHistory.addEventListener('click', () => setJournalTab('history'));
    journalFilterDate?.addEventListener('change', () => void loadJournals(false));
    journalFilterDateAll?.addEventListener('click', () => {
        journalFilterDate.value = '';
        void loadJournals(false);
    });
    journalFilterEventType?.addEventListener('change', () => void loadJournals(false));
    journalFilterSource?.addEventListener('change', () => void loadJournals(false));
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
    authLoginBtn.addEventListener('click', () => void login());
    authRegisterBtn.addEventListener('click', () => void registerUser());
    authTabLogin.addEventListener('click', () => showAuthTab('login'));
    authTabRegister.addEventListener('click', () => showAuthTab('register'));
    authLogoutBtn.addEventListener('click', () => void logout());
    logViewClose.addEventListener('click', closeLogView);
    logViewCloseBtn.addEventListener('click', closeLogView);
    logViewModal.querySelector('.modal-backdrop')?.addEventListener('click', closeLogView);
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
