/**
 * Фронтенд EvilEye — полное покрытие API.
 * Конфиги: list, get, create, update, delete.
 * Runs: list, get, create, start, stop, delete.
 * Streaming: snapshot URL, MJPEG URL, stream:status, stream:stop.
 * System: /ready, /api/v1/version.
 */
import {
  systemApi,
  configsList,
  configGet,
  configCreate,
  configUpdate,
  configDelete,
  runsList,
  runGet,
  runCreate,
  runStart,
  runStop,
  runDelete,
  streamSnapshotUrl,
  streamMjpgUrl,
  streamStatus,
  streamStop,
  type ConfigRun,
} from './api.js';

// ─── DOM ─────────────────────────────────────────────────────────────

const navStreaming = document.getElementById('nav-streaming')!;
const navConfigs = document.getElementById('nav-configs')!;
const navRuns = document.getElementById('nav-runs')!;
const panelStreaming = document.getElementById('panel-streaming')!;
const panelConfigs = document.getElementById('panel-configs')!;
const panelRuns = document.getElementById('panel-runs')!;

const streamingListEl = document.getElementById('streaming-list')!;
const streamingRefreshBtn = document.getElementById('streaming-refresh-btn')!;

const configSearchInput = document.getElementById('config-search') as HTMLInputElement;
const configsListEl = document.getElementById('configs-list')!;
const configCreateBtn = document.getElementById('config-create-btn')!;
const configModal = document.getElementById('config-modal')!;
const configModalTitle = document.getElementById('config-modal-title')!;
const configNameInput = document.getElementById('config-name') as HTMLInputElement;
const configBodyTextarea = document.getElementById('config-body') as HTMLTextAreaElement;
const configSaveBtn = document.getElementById('config-save-btn')!;
const configModalClose = document.getElementById('config-modal-close')!;
const configCloseBtn = document.getElementById('config-close-btn')!;

const runSearchInput = document.getElementById('run-search') as HTMLInputElement;
const runsListEl = document.getElementById('runs-list')!;
const runRefreshBtn = document.getElementById('run-refresh-btn')!;
const runConfigSelect = document.getElementById('run-config-select') as HTMLSelectElement;
const runNameInput = document.getElementById('run-name') as HTMLInputElement;
const runCreateBtn = document.getElementById('run-create-btn')!;
const runUseBodyCheck = document.getElementById('run-use-body') as HTMLInputElement;
const runBodyWrap = document.getElementById('run-body-wrap')!;
const runBodyTextarea = document.getElementById('run-body') as HTMLTextAreaElement;

const runDetailModal = document.getElementById('run-detail-modal')!;
const runDetailRid = document.getElementById('run-detail-rid')!;
const runDetailName = document.getElementById('run-detail-name')!;
const runDetailState = document.getElementById('run-detail-state')!;
const runDetailConfigPath = document.getElementById('run-detail-config-path')!;
const runDetailPid = document.getElementById('run-detail-pid')!;
const runDetailError = document.getElementById('run-detail-error')!;
const runDetailActions = document.getElementById('run-detail-actions')!;
const runDetailClose = document.getElementById('run-detail-close')!;

const streamContainer = document.getElementById('stream-container')!;
const streamRidEl = document.getElementById('stream-rid')!;
const streamNameEl = document.getElementById('stream-name')!;
const streamStateEl = document.getElementById('stream-state')!;
const streamStatusEl = document.getElementById('stream-status')!;
const streamFrame = document.getElementById('stream-frame') as HTMLImageElement;
const streamSnapshotImg = document.getElementById('stream-snapshot') as HTMLImageElement;
const streamBackBtn = document.getElementById('stream-back-btn')!;
const streamFpsInput = document.getElementById('stream-fps-input') as HTMLInputElement;
const streamApplyFpsBtn = document.getElementById('stream-apply-fps-btn')!;
const streamSnapshotBtn = document.getElementById('stream-snapshot-btn')!;

const footerVersion = document.getElementById('footer-version')!;
const errorToast = document.getElementById('error-toast')!;
const successToast = document.getElementById('success-toast')!;

let currentStreamRid: number | null = null;
let streamPollTimer: number | null = null;
let configEditName: string | null = null;
let runsCache: ConfigRun[] = [];
let configNamesCache: string[] = [];

// ─── Toasts ───────────────────────────────────────────────────────────

function showError(msg: string): void {
  errorToast.textContent = msg;
  errorToast.classList.add('show');
  setTimeout(() => errorToast.classList.remove('show'), 4000);
}

function showSuccess(msg: string): void {
  successToast.textContent = msg;
  successToast.classList.add('show');
  setTimeout(() => successToast.classList.remove('show'), 3000);
}

function escapeHtml(s: string): string {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

// ─── System: ready + version ───────────────────────────────────────────

async function loadSystemInfo(): Promise<void> {
  try {
    const v = await systemApi.version();
    footerVersion.textContent = `EvilEye ${v.evileye}`;
  } catch {
    footerVersion.textContent = '—';
  }
}

// ─── Navigation ────────────────────────────────────────────────────────

function showPanel(panel: 'streaming' | 'configs' | 'runs'): void {
  panelStreaming.classList.toggle('active', panel === 'streaming');
  panelConfigs.classList.toggle('active', panel === 'configs');
  panelRuns.classList.toggle('active', panel === 'runs');
  navStreaming.classList.toggle('active', panel === 'streaming');
  navConfigs.classList.toggle('active', panel === 'configs');
  navRuns.classList.toggle('active', panel === 'runs');
}

// ─── Configs (list + search, get/create/update/delete) ────────────────

function renderConfigsList(names: string[], searchQuery: string): void {
  const q = searchQuery.trim().toLowerCase();
  const filtered = q ? names.filter((n) => n.toLowerCase().includes(q)) : names;
  configsListEl.innerHTML =
    filtered.length === 0
      ? '<li class="empty">' + (q ? 'Ничего не найдено.' : 'Конфигов пока нет. Создайте первый.') + '</li>'
      : filtered
          .map(
            (n) =>
              `<li class="config-item" data-name="${n.replace(/"/g, '&quot;')}">
                <span class="config-name">${escapeHtml(n)}</span>
                <div class="config-actions">
                  <button type="button" class="btn btn-sm btn-outline config-view" data-name="${n.replace(/"/g, '&quot;')}">Просмотр</button>
                  <button type="button" class="btn btn-sm btn-outline config-edit" data-name="${n.replace(/"/g, '&quot;')}">Изменить</button>
                  <button type="button" class="btn btn-sm btn-danger config-delete" data-name="${n.replace(/"/g, '&quot;')}">Удалить</button>
                </div>
              </li>`
          )
          .join('');
}

async function loadConfigs(): Promise<void> {
  try {
    const names = await configsList();
    configNamesCache = names;
    const searchQuery = configSearchInput?.value?.trim() ?? '';
    renderConfigsList(names, searchQuery);
    runConfigSelect.innerHTML =
      '<option value="">Выберите конфиг</option>' + names.map((n) => `<option value="${n}">${n}</option>`).join('');
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Не удалось загрузить конфиги');
  }
}

function openConfigModal(mode: 'create' | 'edit' | 'view', name?: string): void {
  configEditName = name ?? null;
  const isView = mode === 'view';
  const isCreate = mode === 'create';
  configModalTitle.textContent = isCreate ? 'Новый конфиг' : isView ? `Просмотр: ${name}` : `Редактировать ${name}`;
  configNameInput.value = name ?? '';
  configNameInput.disabled = isView || mode === 'edit';
  configBodyTextarea.value = '{}';
  configBodyTextarea.readOnly = isView;
  configBodyTextarea.classList.toggle('readonly', isView);
  (configSaveBtn as HTMLElement).style.display = isView ? 'none' : '';
  configCloseBtn.style.display = '';
  if ((mode === 'edit' || mode === 'view') && name) {
    configGet(name)
      .then((body) => {
        configBodyTextarea.value = JSON.stringify(body, null, 2);
      })
      .catch((e) => showError(e instanceof Error ? e.message : 'Не удалось загрузить конфиг'));
  }
  configModal.classList.add('open');
}

function closeConfigModal(): void {
  configModal.classList.remove('open');
  configEditName = null;
  configBodyTextarea.readOnly = false;
  configBodyTextarea.classList.remove('readonly');
  (configSaveBtn as HTMLElement).style.display = '';
}

async function saveConfig(): Promise<void> {
  const nameRaw = configNameInput.value?.trim();
  if (!nameRaw) {
    showError('Укажите имя конфига');
    return;
  }
  const name = nameRaw.endsWith('.json') ? nameRaw : `${nameRaw}.json`;
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(configBodyTextarea.value || '{}');
  } catch {
    showError('Неверный JSON в конфигурации');
    return;
  }
  (configSaveBtn as HTMLButtonElement).disabled = true;
  try {
    if (configEditName) {
      await configUpdate(configEditName, body);
      showSuccess('Конфиг обновлён');
    } else {
      await configCreate(name, body);
      showSuccess('Конфиг создан');
    }
    closeConfigModal();
    await loadConfigs();
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Не удалось сохранить конфиг');
  } finally {
    (configSaveBtn as HTMLButtonElement).disabled = false;
  }
}

async function deleteConfig(name: string): Promise<void> {
  if (!confirm(`Удалить конфиг «${name}»?`)) return;
  try {
    await configDelete(name);
    showSuccess('Конфиг удалён');
    await loadConfigs();
    closeConfigModal();
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Не удалось удалить конфиг');
  }
}

// ─── Runs (list + search, get/create/start/stop/delete, detail modal) ───

const stateLabels: Record<string, string> = {
  running: 'running',
  stopped: 'stopped',
  error: 'error',
  created: 'created',
  starting: 'starting',
  stopping: 'stopping',
};

function stateBadge(state: string): string {
  const c =
    state === 'running'
      ? 'badge-running'
      : state === 'stopped' || state === 'error'
        ? 'badge-stopped'
        : 'badge-pending';
  const label = stateLabels[state] ?? state;
  return `<span class="badge ${c}">${escapeHtml(label)}</span>`;
}

function renderRunsList(runs: ConfigRun[], searchQuery: string): void {
  const q = searchQuery.trim().toLowerCase();
  const filtered = q
    ? runs.filter(
        (r) =>
          String(r.id).includes(q) ||
          (r.name ?? '').toLowerCase().includes(q) ||
          (r.config_path ?? '').toLowerCase().includes(q) ||
          (r.state ?? '').toLowerCase().includes(q)
      )
    : runs;
  runsListEl.innerHTML =
    filtered.length === 0
      ? '<li class="empty">' + (q ? 'Ничего не найдено.' : 'Пайплайнов пока нет. Создайте выше.') + '</li>'
      : filtered
          .map(
            (r) => `
        <li class="run-item" data-rid="${r.id}">
          <div class="run-info">
            <span class="run-name">${escapeHtml(r.name ?? `Пайплайн ${r.id}`)}</span>
            <span class="run-id">#${r.id}</span>
            ${stateBadge(r.state)}
            <span class="run-config">${escapeHtml(r.config_path)}</span>
            ${r.error ? `<span class="run-error">${escapeHtml(r.error)}</span>` : ''}
          </div>
          <div class="run-actions">
            <button type="button" class="btn btn-sm btn-outline run-detail" data-rid="${r.id}">Просмотр</button>
            ${r.state === 'running'
              ? `<button type="button" class="btn btn-sm btn-danger run-stop" data-rid="${r.id}">Остановить</button>
                 <button type="button" class="btn btn-sm btn-primary run-stream" data-rid="${r.id}">Поток</button>`
              : `<button type="button" class="btn btn-sm btn-success run-start" data-rid="${r.id}">Запустить</button>
                 <button type="button" class="btn btn-sm btn-outline run-delete" data-rid="${r.id}">Удалить</button>`
            }
          </div>
        </li>`
          )
          .join('');
}

async function loadRuns(): Promise<void> {
  try {
    const map = await runsList();
    runsCache = Object.entries(map)
      .map(([id, r]) => ({ ...r, id: Number(id) }))
      .sort((a, b) => a.id - b.id);
    const searchQuery = runSearchInput?.value?.trim() ?? '';
    renderRunsList(runsCache, searchQuery);
    renderStreamingList();
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Не удалось загрузить список пайплайнов');
  }
}

// ─── Видеопотоки (главная задача пайплайна) ─────────────────────────────

function renderStreamingList(): void {
  const running = runsCache.filter((r) => r.state === 'running');
  const ts = Date.now();
  if (running.length === 0) {
    streamingListEl.innerHTML = `
      <div class="streaming-empty">
        <p class="streaming-empty-title">Нет работающих пайплайнов</p>
        <p class="streaming-empty-hint">На вкладке «Пайплайны» создайте пайплайн и нажмите «Запустить» — здесь появятся карточки с Snapshot, Stream Status, MJPEG Stream и Stop Stream.</p>
      </div>`;
    return;
  }
  streamingListEl.innerHTML = running
    .map(
      (r) => `
    <div class="streaming-card" data-rid="${r.id}">
      <div class="streaming-card-head">
        <span class="streaming-card-name">${escapeHtml(r.name ?? `Пайплайн ${r.id}`)}</span>
        <span class="streaming-card-id">#${r.id}</span>
        <span class="badge badge-running">running</span>
      </div>
      <div class="streaming-api-block" data-api="snapshot">
        <span class="streaming-block-title">GET snapshot</span>
        <div class="streaming-card-preview">
          <img src="${streamSnapshotUrl(r.id)}?t=${ts}" alt="Snapshot" class="streaming-card-snapshot" data-rid="${r.id}">
        </div>
        <button type="button" class="btn btn-sm btn-outline streaming-refresh-snapshot" data-rid="${r.id}">Обновить кадр</button>
      </div>
      <div class="streaming-api-block" data-api="status">
        <span class="streaming-block-title">GET stream:status (MJPEG viewer connection)</span>
        <span class="streaming-status-text" data-rid="${r.id}">—</span>
        <button type="button" class="btn btn-sm btn-outline streaming-refresh-status" data-rid="${r.id}">Обновить статус</button>
        <p class="streaming-status-hint">Active — когда поток открыт в плеере</p>
      </div>
      <div class="streaming-api-block" data-api="mjpeg">
        <span class="streaming-block-title">GET stream.mjpg</span>
        <button type="button" class="btn btn-primary streaming-open" data-rid="${r.id}">Открыть видеопоток</button>
      </div>
    </div>`
    )
    .join('');
  streamingListEl.querySelectorAll('.streaming-open').forEach((btn) => {
    btn.addEventListener('click', () => openStream(Number((btn as HTMLElement).dataset.rid)));
  });
  streamingListEl.querySelectorAll('.streaming-refresh-snapshot').forEach((btn) => {
    btn.addEventListener('click', () => {
      const rid = Number((btn as HTMLElement).dataset.rid);
      const img = streamingListEl.querySelector(`.streaming-card-snapshot[data-rid="${rid}"]`) as HTMLImageElement;
      if (img) img.src = `${streamSnapshotUrl(rid)}?t=${Date.now()}`;
    });
  });
  streamingListEl.querySelectorAll('.streaming-refresh-status').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const rid = Number((btn as HTMLElement).dataset.rid);
      const span = streamingListEl.querySelector(`.streaming-status-text[data-rid="${rid}"]`);
      if (!span) return;
      span.textContent = '…';
      try {
        const st = await streamStatus(rid);
        span.textContent = st.stream_active ? 'Active' : 'Inactive';
      } catch {
        span.textContent = 'Error';
      }
    });
  });
  // Auto-fetch stream:status so user sees current value (Inactive until stream is open)
  running.forEach((r) => {
    const span = streamingListEl.querySelector(`.streaming-status-text[data-rid="${r.id}"]`);
    if (!span) return;
    streamStatus(r.id)
      .then((st) => {
        span.textContent = st.stream_active ? 'Active' : 'Inactive';
      })
      .catch(() => {
        span.textContent = '—';
      });
  });
}

function openRunDetail(rid: number): void {
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
      runDetailName.textContent = run.name ?? `Пайплайн ${rid}`;
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
          ? `<button type="button" class="btn btn-sm btn-danger run-detail-stop" data-rid="${rid}">Остановить</button>
             <button type="button" class="btn btn-sm btn-primary run-detail-stream" data-rid="${rid}">Поток</button>`
          : `<button type="button" class="btn btn-sm btn-success run-detail-start" data-rid="${rid}">Запустить</button>
             <button type="button" class="btn btn-sm btn-outline run-detail-delete" data-rid="${rid}">Удалить</button>`;
      runDetailActions.querySelectorAll('[data-rid]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const r = Number((btn as HTMLElement).dataset.rid);
          if (btn.classList.contains('run-detail-start')) startRun(r);
          else if (btn.classList.contains('run-detail-stop')) stopRun(r);
          else if (btn.classList.contains('run-detail-delete')) deleteRun(r);
          else if (btn.classList.contains('run-detail-stream')) {
            closeRunDetail();
            openStream(r);
          }
        });
      });
    })
    .catch((e) => showError(e instanceof Error ? e.message : 'Не удалось загрузить данные пайплайна'));
}

function closeRunDetail(): void {
  runDetailModal.classList.remove('open');
}

async function createRun(): Promise<void> {
  const useBody = runUseBodyCheck.checked;
  let payload: { name?: string; config_name?: string; config_body?: Record<string, unknown> } = {
    name: runNameInput.value?.trim() || undefined,
  };
  if (useBody) {
    try {
      payload.config_body = JSON.parse(runBodyTextarea.value || '{}');
    } catch {
      showError('Неверный JSON в конфигурации');
      return;
    }
  } else {
    const configName = runConfigSelect.value?.trim();
    if (!configName) {
      showError('Выберите конфиг или вставьте свой JSON');
      return;
    }
    payload.config_name = configName;
  }
  (runCreateBtn as HTMLButtonElement).disabled = true;
  try {
    await runCreate(payload);
    showSuccess('Пайплайн создан');
    await loadRuns();
    runNameInput.value = '';
    if (useBody) runBodyTextarea.value = '{}';
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Не удалось создать пайплайн');
  } finally {
    (runCreateBtn as HTMLButtonElement).disabled = false;
  }
}

async function startRun(rid: number): Promise<void> {
  try {
    await runStart(rid);
    showSuccess('Run started');
    await loadRuns();
    if (runDetailModal.classList.contains('open') && runDetailRid.textContent === String(rid)) {
      openRunDetail(rid);
    }
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Не удалось запустить');
  }
}

async function stopRun(rid: number): Promise<void> {
  try {
    await runStop(rid);
    showSuccess('Run stopped');
    await loadRuns();
    if (runDetailModal.classList.contains('open') && runDetailRid.textContent === String(rid)) {
      openRunDetail(rid);
    }
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Не удалось остановить');
  }
}

async function deleteRun(rid: number): Promise<void> {
  if (!confirm(`Удалить пайплайн ${rid}?`)) return;
  try {
    await runDelete(rid);
    showSuccess('Пайплайн удалён');
    closeRunDetail();
    await loadRuns();
    if (currentStreamRid === rid) closeStream();
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Не удалось удалить пайплайн');
  }
}

// ─── Stream window (snapshot URL, MJPEG URL, stream:status, stream:stop) ─

function openStream(rid: number): void {
  const fps = streamFpsInput?.value ? Number(streamFpsInput.value) : 10;
  if (streamFpsInput) streamFpsInput.value = String(Math.max(1, Math.min(30, fps)));
  currentStreamRid = rid;
  streamRidEl.textContent = String(rid);
  streamNameEl.textContent = '…';
  streamStateEl.textContent = '…';
  streamStatusEl.textContent = '…';
  streamFrame.src = streamMjpgUrl(rid, fps);
  streamSnapshotImg.src = '';
  streamContainer.classList.add('open');
  streamPollTimer = window.setInterval(pollStreamInfo, 3000);
  pollStreamInfo();
}

function applyStreamFps(): void {
  if (currentStreamRid == null) return;
  const fps = streamFpsInput?.value ? Number(streamFpsInput.value) : 10;
  const safeFps = Math.max(1, Math.min(30, fps));
  if (streamFpsInput) streamFpsInput.value = String(safeFps);
  streamFrame.src = streamMjpgUrl(currentStreamRid, safeFps);
  showSuccess(`FPS установлен: ${safeFps}`);
}

function refreshSnapshot(): void {
  if (currentStreamRid == null) return;
  streamSnapshotImg.src = `${streamSnapshotUrl(currentStreamRid)}?t=${Date.now()}`;
}

async function pollStreamInfo(): Promise<void> {
  if (currentStreamRid == null) return;
  try {
    const run = await runGet(currentStreamRid);
    streamNameEl.textContent = run.name ?? `Пайплайн ${run.id}`;
    streamStateEl.textContent = stateLabels[run.state] ?? run.state;
    streamStateEl.className = `badge ${run.state === 'running' ? 'badge-running' : 'badge-stopped'}`;
    const status = await streamStatus(currentStreamRid).catch(() => null);
    if (status) {
      streamStatusEl.textContent = status.stream_active ? 'Active' : 'Inactive';
      streamStatusEl.className = status.stream_active ? 'stream-status-active' : '';
      if (status.stream_active) {
        streamSnapshotImg.src = `${streamSnapshotUrl(currentStreamRid)}?t=${Date.now()}`;
      }
    }
  } catch {
    // ignore
  }
}

function closeStream(): void {
  streamFrame.src = '';
  streamSnapshotImg.src = '';
  streamContainer.classList.remove('open');
  currentStreamRid = null;
  if (streamPollTimer != null) {
    clearInterval(streamPollTimer);
    streamPollTimer = null;
  }
}

// ─── Delegation ───────────────────────────────────────────────────────

function delegateConfigs(e: Event): void {
  const t = (e.target as HTMLElement).closest('[data-name]');
  if (!t) return;
  const name = (t as HTMLElement).dataset.name;
  if (!name) return;
  const target = e.target as HTMLElement;
  if (target.classList.contains('config-view')) {
    openConfigModal('view', name);
  } else if (target.classList.contains('config-edit')) {
    openConfigModal('edit', name);
  } else if (target.classList.contains('config-delete')) {
    deleteConfig(name);
  }
}

function delegateRuns(e: Event): void {
  const t = (e.target as HTMLElement).closest('[data-rid]');
  if (!t) return;
  const rid = Number((t as HTMLElement).dataset.rid);
  if (Number.isNaN(rid)) return;
  const target = e.target as HTMLElement;
  if (target.classList.contains('run-detail')) openRunDetail(rid);
  else if (target.classList.contains('run-start')) startRun(rid);
  else if (target.classList.contains('run-stop')) stopRun(rid);
  else if (target.classList.contains('run-delete')) deleteRun(rid);
  else if (target.classList.contains('run-stream')) openStream(rid);
}

// ─── Init (один запрос за раз при старте) ─────────────────────────────

export function initApp(): void {
  navStreaming.addEventListener('click', () => showPanel('streaming'));
  navConfigs.addEventListener('click', () => showPanel('configs'));
  navRuns.addEventListener('click', () => showPanel('runs'));
  showPanel('streaming');

  streamingRefreshBtn.addEventListener('click', () => loadRuns());

  configCreateBtn.addEventListener('click', () => openConfigModal('create'));
  configModalClose.addEventListener('click', closeConfigModal);
  configModal.querySelector('.modal-backdrop')?.addEventListener('click', closeConfigModal);
  configSaveBtn.addEventListener('click', saveConfig);
  configsListEl.addEventListener('click', delegateConfigs);
  configSearchInput?.addEventListener('input', () => renderConfigsList(configNamesCache, configSearchInput.value ?? ''));

  runUseBodyCheck.addEventListener('change', () => {
    runBodyWrap.classList.toggle('hidden', !runUseBodyCheck.checked);
  });
  runCreateBtn.addEventListener('click', createRun);
  runRefreshBtn.addEventListener('click', () => loadRuns());
  runsListEl.addEventListener('click', delegateRuns);
  runSearchInput?.addEventListener('input', () => renderRunsList(runsCache, runSearchInput.value ?? ''));

  runDetailClose.addEventListener('click', closeRunDetail);
  runDetailModal.querySelector('.modal-backdrop')?.addEventListener('click', closeRunDetail);

  streamBackBtn.addEventListener('click', closeStream);
  streamApplyFpsBtn.addEventListener('click', applyStreamFps);
  streamSnapshotBtn.addEventListener('click', refreshSnapshot);
  configCloseBtn.addEventListener('click', closeConfigModal);

  loadSystemInfo();
  loadConfigs().then(() => loadRuns());
}
