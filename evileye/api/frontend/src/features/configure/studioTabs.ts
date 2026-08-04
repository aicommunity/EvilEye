import type { StudioTab } from '../../api';

/** Client-side fallback if API returns only legacy `sections`. */
export function tabsFromLegacySections(sections: string[]): StudioTab[] {
  const order = [
    'sources',
    'record',
    'preprocess',
    'detectors',
    'trackers',
    'mc_trackers',
    'events_detectors',
    'events',
    'events_processor',
    'objects_handler',
    'visualizer',
    'controller',
    'server',
    'database',
    'database_adapters',
    'storage_monitor',
  ];
  const set = new Set(sections);
  const tabs: StudioTab[] = [];
  for (const id of order) {
    if (set.has(id)) {
      tabs.push({ id: id === 'events' ? 'events_detectors' : id, path: id, label_key: `studio.tab.${id}` });
      set.delete(id);
    }
  }
  for (const id of sections) {
    if (set.has(id) && id !== 'pipeline') {
      tabs.push({ id, path: id, label_key: `studio.tab.${id}` });
    }
  }
  return tabs;
}

export function stableStringify(value: unknown): string {
  return JSON.stringify(value, (_k, v) => v, 0) ?? 'null';
}

export function configBasename(configPath: string | null | undefined): string | null {
  if (!configPath) return null;
  const normalized = configPath.replace(/\\/g, '/');
  const parts = normalized.split('/');
  return parts[parts.length - 1] || null;
}
