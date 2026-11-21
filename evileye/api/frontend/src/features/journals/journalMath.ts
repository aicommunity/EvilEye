export type JournalType = 'events' | 'objects';

import type { JournalGroupedRow } from '../../api';

/** Strip userinfo from rtsp/http URLs so credentials never render in the journal UI. */
export function redactMediaCredentials(text: unknown): string {
  const raw = String(text ?? '');
  if (!raw) return raw;
  return raw.replace(/(rtsp[s]?|https?):\/\/[^/@\s]+@/gi, '$1://');
}

export function rowKey(row: JournalGroupedRow): string {
  return String(row.row_key ?? `${row.time}|${row.event}|${row.information}`);
}

export function eventTypeLabel(t: (key: string) => string, eventType: string): string {
  if (!eventType) return eventType;
  const key = `journals.eventTypes.${eventType}`;
  const translated = t(key);
  return translated !== key ? translated : eventType;
}

export function formatJournalTime(value: unknown, localeTag = 'ru-RU'): string {
  const raw = String(value ?? '').trim();
  if (!raw) return '—';
  const parsed = raw.includes('T') ? raw : raw.replace(' ', 'T');
  const date = new Date(parsed);
  if (Number.isNaN(date.getTime())) {
    return raw.replace('T', ' ').replace(/\.\d+/, '').slice(0, 19);
  }
  return date.toLocaleString(localeTag, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function journalTimeSortKey(value: unknown): number {
  const raw = String(value ?? '').trim();
  if (!raw) return 0;
  const parsed = raw.includes('T') ? raw : raw.replace(' ', 'T');
  const ms = Date.parse(parsed);
  return Number.isNaN(ms) ? 0 : ms;
}

export function sortJournalRowsDesc(rows: JournalGroupedRow[]): JournalGroupedRow[] {
  return [...rows].sort((a, b) => journalTimeSortKey(b.time) - journalTimeSortKey(a.time));
}

export function mergePrependRows(
  existing: JournalGroupedRow[],
  incoming: JournalGroupedRow[],
): { rows: JournalGroupedRow[]; added: number } {
  if (!incoming.length) return { rows: existing, added: 0 };
  const compareLen = Math.max(1, incoming.length);
  const existingKeys = new Set(existing.slice(0, compareLen).map(rowKey));
  const fresh: JournalGroupedRow[] = [];
  for (const row of incoming) {
    const key = rowKey(row);
    if (existingKeys.has(key)) break;
    fresh.push(row);
  }
  if (!fresh.length) return { rows: existing, added: 0 };
  const merged = sortJournalRowsDesc([...fresh, ...existing]).slice(0, 500);
  return { rows: merged, added: fresh.length };
}

export function bboxSvg(
  bbox: number[] | null | undefined,
  zone: number[][] | null | undefined,
): string {
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
  return parts.join('');
}

export function letterboxRect(
  containerW: number,
  containerH: number,
  naturalW: number,
  naturalH: number,
): { left: number; top: number; width: number; height: number } {
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

export function unixFromJournalTime(value: unknown): number | null {
  const raw = String(value ?? '').trim();
  if (!raw) return null;
  const parsed = raw.includes('T') ? raw : raw.replace(' ', 'T');
  const ms = Date.parse(parsed);
  return Number.isNaN(ms) ? null : Math.floor(ms / 1000);
}
