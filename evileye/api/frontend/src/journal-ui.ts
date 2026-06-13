import {
  journalFrameUrl,
  journalPreviewUrl,
  journalVideoUrl,
  type JournalGroupedRow,
} from './api.js';

export type JournalType = 'events' | 'objects';

export function rowKey(row: JournalGroupedRow): string {
  return String(row.row_key ?? `${row.time}|${row.event}|${row.information}`);
}

export function mergePrependRows(
  existing: JournalGroupedRow[],
  incoming: JournalGroupedRow[],
): JournalGroupedRow[] {
  const keys = new Set(existing.map(rowKey));
  const fresh = incoming.filter((row) => !keys.has(rowKey(row)));
  if (!fresh.length) return existing;
  return [...fresh, ...existing].slice(0, 500);
}

let detailOpen = false;

export function isJournalDetailOpen(): boolean {
  return detailOpen;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function bboxSvg(bbox: number[] | null | undefined, zone: number[][] | null | undefined): string {
  const parts: string[] = [];
  if (bbox && bbox.length === 4) {
    const [x1, y1, x2, y2] = bbox;
    parts.push(
      `<rect x="${x1 * 100}%" y="${y1 * 100}%" width="${(x2 - x1) * 100}%" height="${(y2 - y1) * 100}%" fill="none" stroke="#22c55e" stroke-width="2"/>`,
    );
  }
  if (zone && zone.length >= 3) {
    const points = zone.map(([x, y]) => `${x * 100},${y * 100}`).join(' ');
    parts.push(`<polygon points="${points}" fill="rgba(59,130,246,0.15)" stroke="#3b82f6" stroke-width="2"/>`);
  }
  if (!parts.length) return '';
  return `<svg class="journal-preview-overlay" viewBox="0 0 100 100" preserveAspectRatio="none">${parts.join('')}</svg>`;
}

function previewImagePath(row: JournalGroupedRow, mode: 'found' | 'lost'): string {
  return mode === 'found' ? String(row.preview ?? '') : String(row.lost_preview ?? '');
}

function previewUrl(row: JournalGroupedRow, journalType: JournalType, mode: 'found' | 'lost'): string {
  const path = previewImagePath(row, mode);
  if (!path) return '';
  return journalPreviewUrl({
    path,
    date: String(row.date_folder ?? ''),
    journalType,
    mode,
  });
}

function renderPreviewCell(row: JournalGroupedRow, journalType: JournalType): string {
  const hasFound = Boolean(row.has_found_preview || row.preview);
  const hasLost = Boolean(row.has_lost_preview || row.lost_preview);
  const hasVideo =
    journalType === 'events'
      ? Boolean(row.has_found_video || row.has_lost_video)
      : Boolean(row.has_stream_video);
  if (!hasFound && !hasLost && !hasVideo) {
    return '<td>—</td>';
  }
  const mode = hasFound ? 'found' : 'lost';
  const imgUrl = previewUrl(row, journalType, mode);
  const controls: string[] = [];
  if (hasFound && hasLost) {
    controls.push(
      `<button type="button" class="journal-preview-btn${mode === 'found' ? ' active' : ''}" data-mode="found">Found</button>`,
      `<button type="button" class="journal-preview-btn${mode === 'lost' ? ' active' : ''}" data-mode="lost">Lost</button>`,
    );
  }
  if (hasVideo) {
    controls.push('<button type="button" class="journal-preview-btn" data-action="play">▶</button>');
  }
  const bbox = mode === 'found' ? row.bbox_found : row.bbox_lost;
  const zone = mode === 'found' ? row.zone_coords : null;
  return `<td class="journal-preview-cell" data-row-key="${escapeHtml(rowKey(row))}">
    <div class="journal-preview-inner" data-mode="${mode}" data-journal-type="${journalType}">
      ${imgUrl ? `<img class="journal-preview-img" src="${escapeHtml(imgUrl)}" alt="preview">` : '<div class="journal-preview-empty">—</div>'}
      ${bboxSvg(bbox as number[] | null, zone as number[][] | null)}
      ${controls.length ? `<div class="journal-preview-controls">${controls.join('')}</div>` : ''}
    </div>
  </td>`;
}

export function bindJournalRowsMap(items: JournalGroupedRow[]): Map<string, JournalGroupedRow> {
  return new Map(items.map((row) => [rowKey(row), row]));
}

export interface ScrollAnchor {
  key: string;
  offset: number;
}

function scrollContainerFor(container: HTMLElement): HTMLElement {
  return container.classList.contains('journal-table-wrap')
    ? container
    : (container.closest('.journal-table-wrap') as HTMLElement | null) ?? container;
}

export function captureScrollAnchor(container: HTMLElement): ScrollAnchor | null {
  const scroller = scrollContainerFor(container);
  const rows = scroller.querySelectorAll<HTMLElement>('tr[data-row-key]');
  const scrollerTop = scroller.getBoundingClientRect().top;
  for (const row of rows) {
    const rect = row.getBoundingClientRect();
    if (rect.bottom > scrollerTop + 1) {
      return { key: row.dataset.rowKey ?? '', offset: rect.top - scrollerTop };
    }
  }
  return null;
}

export function restoreScrollAnchor(container: HTMLElement, anchor: ScrollAnchor | null): void {
  if (!anchor?.key) return;
  const scroller = scrollContainerFor(container);
  const escaped = anchor.key.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  const row = scroller.querySelector<HTMLElement>(`tr[data-row-key="${escaped}"]`);
  if (!row) return;
  const scrollerTop = scroller.getBoundingClientRect().top;
  const rowTop = row.getBoundingClientRect().top;
  scroller.scrollTop += rowTop - scrollerTop - anchor.offset;
}

export interface RenderJournalOptions {
  append?: boolean;
  preserveScroll?: boolean;
}

export function renderJournalTable(
  container: HTMLElement,
  items: JournalGroupedRow[],
  journalType: JournalType,
  columns: Array<{ key: string; label: string; preview?: boolean }>,
  emptyText: string,
  options: RenderJournalOptions = {},
): void {
  const append = options.append ?? false;
  const preserveScroll = options.preserveScroll ?? false;
  const anchor = preserveScroll ? captureScrollAnchor(container) : null;
  if (!items.length && !append) {
    container.innerHTML = `<p class="empty">${escapeHtml(emptyText)}</p>`;
    return;
  }
  const header = columns.map((col) => `<th>${escapeHtml(col.label)}</th>`).join('');
  const rows = items
    .map((item) => {
      const cells = columns.map((col) => {
        if (col.preview) {
          return renderPreviewCell(item, journalType);
        }
        return `<td>${escapeHtml(String(item[col.key as keyof JournalGroupedRow] ?? '—'))}</td>`;
      });
      return `<tr data-row-key="${escapeHtml(rowKey(item))}">${cells.join('')}</tr>`;
    })
    .join('');
  if (append && container.querySelector('tbody')) {
    container.querySelector('tbody')!.insertAdjacentHTML('beforeend', rows);
    mountJournalPreviewCells(container, bindJournalRowsMap(items));
    return;
  }
  container.innerHTML = `<table class="journal-table"><thead><tr>${header}</tr></thead><tbody>${rows}</tbody></table>`;
  mountJournalPreviewCells(container, bindJournalRowsMap(items));
  if (anchor) restoreScrollAnchor(container, anchor);
}

export function setupJournalInfiniteScroll(
  container: HTMLElement,
  onLoadMore: () => Promise<void>,
): () => void {
  const scroller = scrollContainerFor(container);
  let loading = false;
  const handler = () => {
    if (loading) return;
    const nearBottom =
      scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight * 0.8;
    if (!nearBottom) return;
    loading = true;
    void onLoadMore().finally(() => {
      loading = false;
    });
  };
  scroller.addEventListener('scroll', handler);
  return () => scroller.removeEventListener('scroll', handler);
}

function getModalElements(): {
  modal: HTMLElement;
  body: HTMLElement;
  title: HTMLElement;
  tabs: HTMLElement;
  closeBtn: HTMLButtonElement;
} | null {
  const modal = document.getElementById('journal-detail-modal');
  const body = document.getElementById('journal-detail-body');
  const title = document.getElementById('journal-detail-title');
  const tabs = document.querySelector('.journal-detail-tabs');
  const closeBtn = document.getElementById('journal-detail-close') as HTMLButtonElement | null;
  if (!modal || !body || !title || !tabs || !closeBtn) return null;
  return { modal, body, title, tabs: tabs as HTMLElement, closeBtn };
}

function videoPathForRow(row: JournalGroupedRow, journalType: JournalType, mode: 'found' | 'lost'): string {
  if (journalType === 'objects') {
    return String(row.stream_video_path ?? '');
  }
  return mode === 'found' ? String(row.found_video_path ?? '') : String(row.lost_video_path ?? '');
}

function renderDetailTab(
  body: HTMLElement,
  row: JournalGroupedRow,
  journalType: JournalType,
  tab: 'video' | 'found' | 'lost',
): void {
  if (tab === 'video') {
    const mode: 'found' | 'lost' = row.has_found_video ? 'found' : 'lost';
    const path = videoPathForRow(row, journalType, mode);
    if (!path) {
      body.innerHTML = '<p class="empty">Видео недоступно.</p>';
      return;
    }
    body.innerHTML = `<video class="journal-detail-media" controls src="${escapeHtml(journalVideoUrl({ path }))}"></video>`;
    return;
  }
  const mode = tab;
  const path = previewImagePath(row, mode);
  if (!path) {
    body.innerHTML = '<p class="empty">Изображение недоступно.</p>';
    return;
  }
  const imgUrl = journalFrameUrl({
    path,
    date: String(row.date_folder ?? ''),
    journalType,
    mode,
  });
  const bbox = mode === 'found' ? row.bbox_found : row.bbox_lost;
  const zone = mode === 'found' ? row.zone_coords : null;
  body.innerHTML = `<div class="journal-detail-media-wrap">
    <img class="journal-detail-media" src="${escapeHtml(imgUrl)}" alt="${mode}">
    ${bboxSvg(bbox as number[] | null, zone as number[][] | null)}
  </div>`;
}

export function openJournalDetailModal(row: JournalGroupedRow, journalType: JournalType): void {
  const elements = getModalElements();
  if (!elements) return;
  detailOpen = true;
  const { modal, body, title, tabs, closeBtn } = elements;
  title.textContent = `${row.event ?? 'Event'} — ${row.information ?? ''}`;
  modal.hidden = false;

  const tabDefs: Array<{ id: 'video' | 'found' | 'lost'; label: string; visible: boolean }> = [
    {
      id: 'video',
      label: 'Видео',
      visible: journalType === 'events' ? Boolean(row.has_found_video || row.has_lost_video) : Boolean(row.has_stream_video),
    },
    { id: 'found', label: 'Found', visible: Boolean(row.has_found_preview || row.preview) },
    { id: 'lost', label: 'Lost', visible: Boolean(row.has_lost_preview || row.lost_preview) },
  ];
  const visibleTabs = tabDefs.filter((tab) => tab.visible);
  tabs.innerHTML = visibleTabs
    .map(
      (tab, index) =>
        `<button type="button" class="journal-detail-tab${index === 0 ? ' active' : ''}" data-tab="${tab.id}">${tab.label}</button>`,
    )
    .join('');
  const initialTab = visibleTabs[0]?.id ?? 'found';
  renderDetailTab(body, row, journalType, initialTab);

  tabs.querySelectorAll<HTMLButtonElement>('.journal-detail-tab').forEach((btn) => {
    btn.onclick = () => {
      tabs.querySelectorAll('.journal-detail-tab').forEach((el) => el.classList.remove('active'));
      btn.classList.add('active');
      renderDetailTab(body, row, journalType, btn.dataset.tab as 'video' | 'found' | 'lost');
    };
  });
  closeBtn.onclick = () => closeJournalDetailModal();
  modal.querySelector('.modal-backdrop')?.addEventListener('click', () => closeJournalDetailModal(), { once: true });
}

export function closeJournalDetailModal(): void {
  const modal = document.getElementById('journal-detail-modal');
  const body = document.getElementById('journal-detail-body');
  if (body) body.innerHTML = '';
  if (modal) modal.hidden = true;
  detailOpen = false;
}

function updatePreviewCell(inner: HTMLElement, row: JournalGroupedRow, journalType: JournalType, mode: 'found' | 'lost'): void {
  inner.dataset.mode = mode;
  const img = inner.querySelector<HTMLImageElement>('.journal-preview-img');
  const url = previewUrl(row, journalType, mode);
  if (img && url) {
    img.src = url;
  }
  const oldOverlay = inner.querySelector('.journal-preview-overlay');
  oldOverlay?.remove();
  const bbox = mode === 'found' ? row.bbox_found : row.bbox_lost;
  const zone = mode === 'found' ? row.zone_coords : null;
  const svg = bboxSvg(bbox as number[] | null, zone as number[][] | null);
  if (svg) {
    inner.insertAdjacentHTML('afterbegin', svg);
  }
  inner.querySelectorAll<HTMLButtonElement>('.journal-preview-btn[data-mode]').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });
}

export function mountJournalPreviewCells(container: HTMLElement, rowsByKey?: Map<string, JournalGroupedRow>): void {
  container.querySelectorAll<HTMLElement>('.journal-preview-inner').forEach((inner) => {
    if (inner.dataset.bound === '1') return;
    inner.dataset.bound = '1';
    const cell = inner.closest('.journal-preview-cell');
    const key = cell?.getAttribute('data-row-key') ?? '';
    const row = rowsByKey?.get(key);
    const journalType = (inner.dataset.journalType as JournalType) || 'events';
    if (!row) return;

    inner.querySelectorAll<HTMLButtonElement>('.journal-preview-btn').forEach((btn) => {
      btn.addEventListener('click', (event) => {
        event.stopPropagation();
        if (btn.dataset.action === 'play') {
          openJournalDetailModal(row, journalType);
          return;
        }
        const mode = btn.dataset.mode as 'found' | 'lost' | undefined;
        if (mode) updatePreviewCell(inner, row, journalType, mode);
      });
    });
    inner.querySelector('.journal-preview-img')?.addEventListener('dblclick', () => {
      openJournalDetailModal(row, journalType);
    });
    inner.querySelector('.journal-preview-img')?.addEventListener('click', () => {
      openJournalDetailModal(row, journalType);
    });
  });
}
