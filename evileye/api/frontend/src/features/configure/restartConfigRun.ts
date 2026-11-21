import { runsList, runCreate, runStart, runStop, request } from '../../api';
import { ApiError } from '../../api/client';
import type { ConfigRun } from '../../api/types';
import { configBasename } from './studioTabs';
import { writePendingApply } from './pendingApply';

function pathMatches(configPath: string, configName: string): boolean {
  const base = configBasename(configPath) ?? configPath;
  const want = configBasename(configName) ?? configName;
  return base === want || configPath.endsWith(`/${want}`) || configPath.endsWith(`\\${want}`);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export type SystemRestartResult = {
  mode: string;
  scheduled?: boolean;
  config_name?: string;
  helper_pid?: number;
  pid?: number;
  rid?: number;
  run?: Record<string, unknown>;
};

function assertRestartSucceeded(res: SystemRestartResult): void {
  const run = res.run as { state?: string; error?: string } | undefined;
  if (run?.state === 'error') {
    throw new Error(run.error || 'Pipeline failed to start');
  }
}

function findMatchingRun(runs: Record<number, ConfigRun>, configName: string): ConfigRun | undefined {
  const list = Object.values(runs);
  const matching = list.filter((r) => pathMatches(r.config_path, configName));
  return matching.find((r) => r.state === 'running' || r.alive) ?? matching[0];
}

/** Poll runs until the config pipeline is alive or timeout. */
export async function waitForConfigRunAlive(
  configName: string,
  { attempts = 5, intervalMs = 800 }: { attempts?: number; intervalMs?: number } = {},
): Promise<ConfigRun> {
  for (let i = 0; i < attempts; i++) {
    const runs = await runsList();
    const run = findMatchingRun(runs, configName);
    if (run && (run.alive || run.state === 'running')) {
      return run;
    }
    if (i + 1 < attempts) {
      await sleep(intervalMs);
    }
  }
  throw new Error('Pipeline did not start');
}

/** Prefer safe server-side restart (handles embedded API / self-hosted pipeline). */
export async function restartConfigRun(configName: string): Promise<SystemRestartResult> {
  // Clear pending banner before the call so a connection drop on self-hosted
  // shutdown does not leave a stale "not applied" warning.
  writePendingApply(configName, false);

  let res: SystemRestartResult;
  try {
    res = await request<SystemRestartResult>('/system/restart', {
      method: 'POST',
      body: JSON.stringify({ config_name: configName }),
    });
  } catch (err) {
    // Only fall back for older APIs that lack /system/restart (404).
    // A catch-all fallback (stop→create→start) races a hung server restart and
    // leaves orphan ConfigRun rows in "created" that break Live WS.
    const status = err instanceof ApiError ? err.status : 0;
    if (status !== 404) {
      throw err;
    }
    const runs = await runsList();
    const list = Object.values(runs);
    const matching = list.filter((r) => pathMatches(r.config_path, configName));
    const running = matching.find((r) => r.state === 'running' || r.alive);
    if (running?.id != null) {
      await runStop(running.id);
    }
    const run = await runCreate({ config_name: configName });
    await runStart(run.id as number);
    await waitForConfigRunAlive(configName);
    return {
      mode: 'managed_restart_fallback',
      scheduled: false,
      config_name: configName,
      run: run as unknown as Record<string, unknown>,
    };
  }

  assertRestartSucceeded(res);
  if (!res.scheduled) {
    await waitForConfigRunAlive(configName);
  }
  return res;
}
