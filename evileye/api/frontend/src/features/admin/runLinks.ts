import type { StateRun } from '../../api';

/** Basename of a run's config path / config_name. */
export function runConfigName(run: Pick<StateRun, 'config_name' | 'config_path'>): string | null {
  if (run.config_name) return run.config_name;
  const path = run.config_path;
  if (!path) return null;
  const parts = path.replace(/\\/g, '/').split('/');
  return parts[parts.length - 1] || null;
}

export function matchRunConfig(
  run: Pick<StateRun, 'config_name' | 'config_path'>,
  configName: string | null | undefined,
): boolean {
  if (!configName) return true;
  const name = runConfigName(run);
  return name === configName;
}

export function runMainLogFile(run: Pick<StateRun, 'log_files'>): string | null {
  return run.log_files?.main ?? null;
}

export function logFileHref(filename: string): string {
  return `/admin/logs?file=${encodeURIComponent(filename)}`;
}

export function configStudioHref(configName: string, tab?: string): string {
  const base = `/admin/configs/${encodeURIComponent(configName)}`;
  return tab ? `${base}?tab=${encodeURIComponent(tab)}` : base;
}

export function runsHubHref(opts: { config?: string | null; highlight?: number | null }): string {
  const p = new URLSearchParams();
  if (opts.config) p.set('config', opts.config);
  if (opts.highlight != null) p.set('highlight', String(opts.highlight));
  const qs = p.toString();
  return qs ? `/admin/runs?${qs}` : '/admin/runs';
}

/** Best-effort extract a config filename from DB configuration_info blob. */
export function inferConfigNameFromJob(item: Record<string, unknown>): string | null {
  const info = item.configuration_info;
  if (typeof info === 'string') {
    try {
      return inferConfigNameFromJob({ configuration_info: JSON.parse(info) });
    } catch {
      return null;
    }
  }
  if (!info || typeof info !== 'object') return null;
  const obj = info as Record<string, unknown>;
  for (const key of ['config_path', 'path', 'file', 'filename', 'name']) {
    const v = obj[key];
    if (typeof v === 'string' && v.trim()) {
      const parts = v.replace(/\\/g, '/').split('/');
      const base = parts[parts.length - 1];
      if (base.endsWith('.json')) return base;
      return base.includes('.') ? base : `${base}.json`;
    }
  }
  // Nested controller / common patterns
  const nested = obj.pipeline ?? obj.controller ?? obj.sources;
  if (nested && typeof nested === 'object') {
    const found = inferConfigNameFromJob({ configuration_info: nested });
    if (found) return found;
  }
  return null;
}
