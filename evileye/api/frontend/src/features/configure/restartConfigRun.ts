import { runsList, runCreate, runStart, runStop, request } from '../../api';
import { configBasename } from './studioTabs';
import { writePendingApply } from './pendingApply';

function pathMatches(configPath: string, configName: string): boolean {
  const base = configBasename(configPath) ?? configPath;
  const want = configBasename(configName) ?? configName;
  return base === want || configPath.endsWith(`/${want}`) || configPath.endsWith(`\\${want}`);
}

export type SystemRestartResult = {
  mode: string;
  scheduled?: boolean;
  config_name?: string;
  helper_pid?: number;
  run?: Record<string, unknown>;
};

/** Prefer safe server-side restart (handles embedded API / self-hosted pipeline). */
export async function restartConfigRun(configName: string): Promise<SystemRestartResult> {
  // Clear pending banner before the call so a connection drop on self-hosted
  // shutdown does not leave a stale "not applied" warning.
  writePendingApply(configName, false);

  try {
    return await request<SystemRestartResult>('/system/restart', {
      method: 'POST',
      body: JSON.stringify({ config_name: configName }),
    });
  } catch (err) {
    // Fallback for older API builds: previous stop→create→start path.
    const runs = await runsList();
    const list = Object.values(runs);
    const matching = list.filter((r) => pathMatches(r.config_path, configName));
    const running = matching.find((r) => r.state === 'running' || r.alive);
    if (running?.id != null) {
      await runStop(running.id);
    }
    const run = await runCreate({ config_name: configName });
    await runStart(run.id as number);
    return { mode: 'managed_restart_fallback', scheduled: false, config_name: configName, run: run as unknown as Record<string, unknown> };
  }
}
