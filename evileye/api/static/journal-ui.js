import { journalFrameUrl, journalPreviewUrl, journalVideoUrl, journalsApi, } from './api.js';
export function rowKey(row) {
    return String(row.row_key ?? `${row.time}|${row.event}|${row.information}`);
}
export function formatJournalTime(value) {
    const raw = String(value ?? '').trim();
    if (!raw)
        return '—';
    const parsed = raw.includes('T') ? raw : raw.replace(' ', 'T');
    const date = new Date(parsed);
    if (Number.isNaN(date.getTime())) {
        return raw.replace('T', ' ').replace(/\.\d+/, '').slice(0, 19);
    }
    return date.toLocaleString('ru-RU', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
    });
}
function journalTimeSortKey(value) {
    const raw = String(value ?? '').trim();
    if (!raw)
        return 0;
    const parsed = raw.includes('T') ? raw : raw.replace(' ', 'T');
    const ms = Date.parse(parsed);
    return Number.isNaN(ms) ? 0 : ms;
}
export function sortJournalRowsDesc(rows) {
    return [...rows].sort((a, b) => journalTimeSortKey(b.time) - journalTimeSortKey(a.time));
}
export function mergePrependRows(existing, incoming) {
    if (!incoming.length)
        return { rows: existing, added: 0 };
    const compareLen = Math.max(1, incoming.length);
    const existingKeys = new Set(existing.slice(0, compareLen).map(rowKey));
    const fresh = [];
    for (const row of incoming) {
        const key = rowKey(row);
        if (existingKeys.has(key))
            break;
        fresh.push(row);
    }
    if (!fresh.length)
        return { rows: existing, added: 0 };
    const merged = sortJournalRowsDesc([...fresh, ...existing]).slice(0, 500);
    return { rows: merged, added: fresh.length };
}
let detailOpen = false;
export function isJournalDetailOpen() {
    return detailOpen;
}
function escapeHtml(value) {
    return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
function formatJournalCell(value) {
    return escapeHtml(formatJournalTime(value));
}
function bboxSvg(bbox, zone) {
    const parts = [];
    if (bbox && bbox.length === 4) {
        const [x1, y1, x2, y2] = bbox;
        parts.push(`<rect x="${x1 * 100}%" y="${y1 * 100}%" width="${(x2 - x1) * 100}%" height="${(y2 - y1) * 100}%" fill="none" stroke="#22c55e" stroke-width="2"/>`);
    }
    if (zone && zone.length >= 3) {
        const points = zone.map(([x, y]) => `${x * 100},${y * 100}`).join(' ');
        parts.push(`<polygon points="${points}" fill="rgba(59,130,246,0.15)" stroke="#3b82f6" stroke-width="2"/>`);
    }
    if (!parts.length)
        return '';
    return `<svg class="journal-preview-overlay" viewBox="0 0 100 100" preserveAspectRatio="none">${parts.join('')}</svg>`;
}
function letterboxRect(containerW, containerH, naturalW, naturalH) {
    if (!containerW || !containerH || !naturalW || !naturalH) {
        return { left: 0, top: 0, width: containerW, height: containerH };
    }
    const scale = Math.min(containerW / naturalW, containerH / naturalH);
    const width = naturalW * scale;
    const height = naturalH * scale;
    return {
        left: (containerW - width) / 2,
        top: (containerH - height) / 2,
        width,
        height,
    };
}
function applyPreviewOverlay(inner, bbox, zone, imgSelector = '.journal-preview-img') {
    const img = inner.querySelector(imgSelector);
    if (!img || !img.naturalWidth)
        return;
    let wrap = inner.querySelector('.journal-preview-overlay-wrap');
    if (!wrap) {
        wrap = document.createElement('div');
        wrap.className = 'journal-preview-overlay-wrap';
        inner.appendChild(wrap);
    }
    const containerW = inner.clientWidth || img.offsetWidth;
    const containerH = inner.clientHeight || img.offsetHeight;
    const box = letterboxRect(containerW, containerH, img.naturalWidth, img.naturalHeight);
    Object.assign(wrap.style, {
        left: `${box.left}px`,
        top: `${box.top}px`,
        width: `${box.width}px`,
        height: `${box.height}px`,
    });
    wrap.innerHTML = bboxSvg(bbox, zone);
}
function previewImagePath(row, mode) {
    return mode === 'found' ? String(row.preview ?? '') : String(row.lost_preview ?? '');
}
function previewUrl(row, journalType, mode) {
    const path = previewImagePath(row, mode);
    if (!path)
        return '';
    return journalPreviewUrl({
        path,
        date: String(row.date_folder ?? ''),
        journalType,
        mode,
    });
}
function frameUrl(row, journalType, mode) {
    const path = previewImagePath(row, mode);
    if (!path)
        return '';
    return journalFrameUrl({
        path,
        date: String(row.date_folder ?? ''),
        journalType,
        mode,
    });
}
/** Таблица: только preview (маленький файл). Полный frame — в модалке. */
function tableImageUrl(row, journalType, mode) {
    return previewUrl(row, journalType, mode) || frameUrl(row, journalType, mode);
}
function imageUrlFallbacks(row, journalType, mode) {
    const preview = previewUrl(row, journalType, mode);
    const frame = frameUrl(row, journalType, mode);
    return [preview, frame].filter((url, index, all) => Boolean(url) && all.indexOf(url) === index);
}
function mountDetailImage(body, row, journalType, mode) {
    const path = previewImagePath(row, mode);
    if (!path) {
        body.innerHTML = '<p class="empty">Изображение недоступно.</p>';
        return;
    }
    const urls = imageUrlFallbacks(row, journalType, mode);
    if (!urls.length) {
        body.innerHTML = '<p class="empty">Изображение недоступно.</p>';
        return;
    }
    const bbox = mode === 'found' ? row.bbox_found : row.bbox_lost;
    const zone = mode === 'found' ? row.zone_coords : null;
    body.innerHTML = `<div class="journal-detail-media-wrap">
    <img class="journal-detail-media" src="${escapeHtml(urls[0])}" alt="${mode}" loading="eager" decoding="async">
  </div>`;
    const wrap = body.querySelector('.journal-detail-media-wrap');
    const img = body.querySelector('.journal-detail-media');
    if (!wrap || !img)
        return;
    let urlIndex = 0;
    const applyOverlay = () => applyPreviewOverlay(wrap, bbox, zone, '.journal-detail-media');
    const tryNext = () => {
        urlIndex += 1;
        if (urlIndex >= urls.length) {
            body.innerHTML = '<p class="empty">Изображение недоступно.</p>';
            return;
        }
        img.src = urls[urlIndex];
    };
    img.addEventListener('load', applyOverlay);
    img.addEventListener('error', tryNext);
    if (img.complete && img.naturalWidth > 0)
        applyOverlay();
}
function renderPreviewCell(row, journalType) {
    const hasFound = Boolean(row.has_found_preview || row.preview);
    const hasLost = Boolean(row.has_lost_preview || row.lost_preview);
    const hasVideo = journalType === 'events'
        ? Boolean(row.has_found_video || row.has_lost_video)
        : Boolean(row.has_stream_video);
    if (!hasFound && !hasLost && !hasVideo) {
        return '<td>—</td>';
    }
    const mode = hasFound ? 'found' : 'lost';
    const imgUrl = tableImageUrl(row, journalType, mode);
    const controls = [];
    if (hasFound && hasLost) {
        controls.push(`<button type="button" class="journal-preview-btn${mode === 'found' ? ' active' : ''}" data-mode="found">Found</button>`, `<button type="button" class="journal-preview-btn${mode === 'lost' ? ' active' : ''}" data-mode="lost">Lost</button>`);
    }
    if (hasVideo) {
        controls.push('<button type="button" class="journal-preview-btn" data-action="play">▶</button>');
    }
    return `<td class="journal-preview-cell" data-row-key="${escapeHtml(rowKey(row))}">
    <div class="journal-preview-inner" data-mode="${mode}" data-journal-type="${journalType}">
      ${imgUrl ? `<img class="journal-preview-img" src="${escapeHtml(imgUrl)}" alt="preview" loading="lazy" decoding="async">` : '<div class="journal-preview-empty">—</div>'}
      ${controls.length ? `<div class="journal-preview-controls">${controls.join('')}</div>` : ''}
    </div>
  </td>`;
}
function renderTableRow(item, journalType, columns) {
    const cells = columns.map((col) => {
        if (col.preview) {
            return renderPreviewCell(item, journalType);
        }
        if (col.key === 'time' || col.key === 'time_lost') {
            return `<td>${formatJournalCell(item[col.key])}</td>`;
        }
        return `<td>${escapeHtml(String(item[col.key] ?? '—'))}</td>`;
    });
    return `<tr data-row-key="${escapeHtml(rowKey(item))}">${cells.join('')}</tr>`;
}
export function bindJournalRowsMap(items) {
    return new Map(items.map((row) => [rowKey(row), row]));
}
function scrollContainerFor(container) {
    return container.classList.contains('journal-table-wrap')
        ? container
        : container.closest('.journal-table-wrap') ?? container;
}
export function captureScrollAnchor(container) {
    const scroller = scrollContainerFor(container);
    const rows = scroller.querySelectorAll('tr[data-row-key]');
    const scrollerTop = scroller.getBoundingClientRect().top;
    for (const row of rows) {
        const rect = row.getBoundingClientRect();
        if (rect.bottom > scrollerTop + 1) {
            return { key: row.dataset.rowKey ?? '', offset: rect.top - scrollerTop };
        }
    }
    return null;
}
export function restoreScrollAnchor(container, anchor) {
    if (!anchor?.key)
        return;
    const scroller = scrollContainerFor(container);
    const escaped = anchor.key.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    const row = scroller.querySelector(`tr[data-row-key="${escaped}"]`);
    if (!row)
        return;
    const scrollerTop = scroller.getBoundingClientRect().top;
    const rowTop = row.getBoundingClientRect().top;
    scroller.scrollTop += rowTop - scrollerTop - anchor.offset;
}
export function scrollJournalToTopIfFollowing(container) {
    const scroller = scrollContainerFor(container);
    if (scroller.scrollTop <= 50)
        scroller.scrollTop = 0;
}
export function renderJournalTable(container, items, journalType, columns, emptyText, options = {}) {
    const append = options.append ?? false;
    const preserveScroll = options.preserveScroll ?? false;
    const scrollToTop = options.scrollToTop ?? false;
    const anchor = preserveScroll ? captureScrollAnchor(container) : null;
    if (!items.length && !append) {
        container.innerHTML = `<p class="empty">${escapeHtml(emptyText)}</p>`;
        return;
    }
    const header = columns.map((col) => `<th>${escapeHtml(col.label)}</th>`).join('');
    const rows = items.map((item) => renderTableRow(item, journalType, columns)).join('');
    if (append && container.querySelector('tbody')) {
        container.querySelector('tbody').insertAdjacentHTML('beforeend', rows);
        mountJournalPreviewCells(container, bindJournalRowsMap(items));
        return;
    }
    container.innerHTML = `<table class="journal-table"><thead><tr>${header}</tr></thead><tbody>${rows}</tbody></table>`;
    mountJournalPreviewCells(container, bindJournalRowsMap(items));
    if (anchor)
        restoreScrollAnchor(container, anchor);
    if (scrollToTop) {
        requestAnimationFrame(() => scrollJournalToTopIfFollowing(container));
    }
}
export function prependJournalRows(container, newRows, journalType, columns) {
    const tbody = container.querySelector('tbody');
    if (!tbody || !newRows.length)
        return;
    const html = newRows.map((item) => renderTableRow(item, journalType, columns)).join('');
    tbody.insertAdjacentHTML('afterbegin', html);
    mountJournalPreviewCells(container, bindJournalRowsMap(newRows));
    while (tbody.children.length > 500) {
        tbody.removeChild(tbody.lastElementChild);
    }
}
export function setupJournalInfiniteScroll(container, onLoadMore) {
    const scroller = scrollContainerFor(container);
    let loading = false;
    const handler = () => {
        if (loading)
            return;
        const nearBottom = scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight * 0.8;
        if (!nearBottom)
            return;
        loading = true;
        void onLoadMore().finally(() => {
            loading = false;
        });
    };
    scroller.addEventListener('scroll', handler);
    return () => scroller.removeEventListener('scroll', handler);
}
function getModalElements() {
    const modal = document.getElementById('journal-detail-modal');
    const body = document.getElementById('journal-detail-body');
    const title = document.getElementById('journal-detail-title');
    const tabs = document.querySelector('.journal-detail-tabs');
    const closeBtn = document.getElementById('journal-detail-close');
    if (!modal || !body || !title || !tabs || !closeBtn)
        return null;
    return { modal, body, title, tabs: tabs, closeBtn };
}
function videoPathForRow(row, journalType, mode) {
    if (journalType === 'objects') {
        return String(row.stream_video_path ?? '');
    }
    return mode === 'found' ? String(row.found_video_path ?? '') : String(row.lost_video_path ?? '');
}
function mountDetailVideo(body, row, journalType, mode) {
    const primaryPath = videoPathForRow(row, journalType, mode);
    const fallbackMode = mode === 'found' ? 'lost' : 'found';
    const fallbackPath = videoPathForRow(row, journalType, fallbackMode);
    const offsetSec = journalType === 'objects' ? Number(row.stream_offset_seconds ?? 0) : 0;
    const tryPlay = (path, fallback) => {
        if (!path) {
            body.innerHTML = '<p class="empty">Видео недоступно.</p>';
            return;
        }
        body.innerHTML = `<video class="journal-detail-media" controls preload="metadata" src="${escapeHtml(journalVideoUrl({ path }))}"></video>`;
        const video = body.querySelector('.journal-detail-media');
        if (!video)
            return;
        video.addEventListener('loadedmetadata', () => {
            if (offsetSec > 0)
                video.currentTime = offsetSec;
        }, { once: true });
        video.addEventListener('error', () => {
            if (fallback && fallback !== path) {
                tryPlay(fallback);
            }
            else {
                body.innerHTML = '<p class="empty">Видео недоступно.</p>';
            }
        }, { once: true });
    };
    tryPlay(primaryPath, fallbackPath !== primaryPath ? fallbackPath : undefined);
}
function renderDetailTab(body, row, journalType, tab) {
    if (tab === 'video') {
        const mode = row.has_found_video ? 'found' : 'lost';
        mountDetailVideo(body, row, journalType, mode);
        return;
    }
    const mode = tab;
    mountDetailImage(body, row, journalType, mode);
}
export function openJournalDetailModal(row, journalType, options = {}) {
    const elements = getModalElements();
    if (!elements)
        return;
    detailOpen = true;
    const { modal, body, title, tabs, closeBtn } = elements;
    title.textContent = `${row.event ?? 'Event'} — ${row.information ?? ''}`;
    modal.hidden = false;
    modal.classList.add('open');
    let enrichedRow = row;
    let activeTab = 'found';
    const buildTabs = (currentRow) => {
        const hasFound = Boolean(currentRow.has_found_preview || currentRow.preview);
        const hasLost = Boolean(currentRow.has_lost_preview || currentRow.lost_preview);
        const hasVideo = journalType === 'events'
            ? Boolean(currentRow.has_found_video || currentRow.has_lost_video)
            : Boolean(currentRow.has_stream_video);
        const tabDefs = [
            { id: 'found', label: 'Found', visible: hasFound },
            { id: 'lost', label: 'Lost', visible: hasLost },
            { id: 'video', label: 'Видео', visible: hasVideo },
        ];
        return tabDefs.filter((tab) => tab.visible);
    };
    const renderActiveTab = (tabId) => {
        activeTab = tabId;
        tabs.querySelectorAll('.journal-detail-tab').forEach((btn) => {
            btn.classList.toggle('active', btn.dataset.tab === tabId);
        });
        renderDetailTab(body, enrichedRow, journalType, tabId);
    };
    const visibleTabs = buildTabs(enrichedRow);
    tabs.innerHTML = visibleTabs
        .map((tab) => `<button type="button" class="journal-detail-tab" data-tab="${tab.id}">${tab.label}</button>`)
        .join('');
    const cellMode = visibleTabs.some((tab) => tab.id === 'found') ? 'found' : 'lost';
    const preferredTab = options.initialTab ?? cellMode;
    const initialTab = visibleTabs.find((tab) => tab.id === preferredTab)?.id
        ?? visibleTabs.find((tab) => tab.id !== 'video')?.id
        ?? visibleTabs[0]?.id
        ?? 'found';
    renderActiveTab(initialTab);
    tabs.querySelectorAll('.journal-detail-tab').forEach((btn) => {
        btn.onclick = () => {
            renderActiveTab(btn.dataset.tab);
        };
    });
    closeBtn.onclick = () => closeJournalDetailModal();
    modal.querySelector('.modal-backdrop')?.addEventListener('click', () => closeJournalDetailModal(), { once: true });
    void ensureRowBbox(row, journalType).then((metaRow) => {
        if (!detailOpen)
            return;
        enrichedRow = metaRow;
        const updatedTabs = buildTabs(enrichedRow);
        if (updatedTabs.length !== visibleTabs.length) {
            tabs.innerHTML = updatedTabs
                .map((tab) => `<button type="button" class="journal-detail-tab" data-tab="${tab.id}">${tab.label}</button>`)
                .join('');
            tabs.querySelectorAll('.journal-detail-tab').forEach((btn) => {
                btn.onclick = () => {
                    renderActiveTab(btn.dataset.tab);
                };
            });
        }
        renderActiveTab(activeTab);
    });
}
export function closeJournalDetailModal() {
    const modal = document.getElementById('journal-detail-modal');
    const body = document.getElementById('journal-detail-body');
    if (body)
        body.innerHTML = '';
    if (modal) {
        modal.hidden = true;
        modal.classList.remove('open');
    }
    detailOpen = false;
}
async function ensureRowBbox(row, journalType) {
    if (row.bbox_found != null || row.bbox_lost != null)
        return row;
    try {
        const meta = await journalsApi.rowMeta(rowKey(row), journalType);
        return { ...row, ...meta };
    }
    catch {
        return row;
    }
}
function updatePreviewCell(inner, row, journalType, mode) {
    inner.dataset.mode = mode;
    const img = inner.querySelector('.journal-preview-img');
    const url = tableImageUrl(row, journalType, mode);
    if (img && url) {
        img.onload = () => {
            const bbox = mode === 'found' ? row.bbox_found : row.bbox_lost;
            const zone = mode === 'found' ? row.zone_coords : null;
            applyPreviewOverlay(inner, bbox, zone);
        };
        img.src = url;
    }
    inner.querySelectorAll('.journal-preview-btn[data-mode]').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
}
export function mountJournalPreviewCells(container, rowsByKey) {
    container.querySelectorAll('.journal-preview-inner').forEach((inner) => {
        if (inner.dataset.bound === '1')
            return;
        inner.dataset.bound = '1';
        const cell = inner.closest('.journal-preview-cell');
        const key = cell?.getAttribute('data-row-key') ?? '';
        let row = rowsByKey?.get(key);
        const journalType = inner.dataset.journalType || 'events';
        if (!row)
            return;
        const applyOverlayForRow = (r) => {
            const mode = inner.dataset.mode || 'found';
            const bbox = mode === 'found' ? r.bbox_found : r.bbox_lost;
            const zone = mode === 'found' ? r.zone_coords : null;
            applyPreviewOverlay(inner, bbox, zone);
        };
        const img = inner.querySelector('.journal-preview-img');
        if (img) {
            const onLoad = () => {
                void ensureRowBbox(row, journalType).then((enriched) => {
                    row = enriched;
                    applyOverlayForRow(enriched);
                });
            };
            if (img.complete)
                onLoad();
            else
                img.addEventListener('load', onLoad, { once: true });
        }
        inner.querySelectorAll('.journal-preview-btn').forEach((btn) => {
            btn.addEventListener('click', (event) => {
                event.stopPropagation();
                if (!row)
                    return;
                if (btn.dataset.action === 'play') {
                    openJournalDetailModal(row, journalType, { initialTab: 'video' });
                    return;
                }
                const mode = btn.dataset.mode;
                if (mode)
                    updatePreviewCell(inner, row, journalType, mode);
            });
        });
        inner.querySelector('.journal-preview-img')?.addEventListener('dblclick', () => {
            if (row)
                openJournalDetailModal(row, journalType);
        });
        inner.querySelector('.journal-preview-img')?.addEventListener('click', () => {
            if (row)
                openJournalDetailModal(row, journalType);
        });
    });
}
