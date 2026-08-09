import { runsList, runCreate, runStart, runStop } from '../../api';
import { configBasename } from './studioTabs';

function pathMatches(configPath: string, configName: string): boolean {
  const base = configBasename(configPath) ?? configPath;
  const want = configBasename(configName) ?? configName;
  return base === want || configPath.endsWith(`/${want}`) || configPath.endsWith(`\\${want}`);
}

/** Stop a running run for this config (if any), then create and start a fresh run. */
export async function restartConfigRun(configName: string): Promise<void> {
  const runs = await runsList();
  const list = Object.values(runs);
  const matching = list.filter((r) => pathMatches(r.config_path, configName));
  const running = matching.find((r) => r.state === 'running' || r.alive);
  if (running?.id != null) {
    await runStop(running.id);
  }
  const run = await runCreate({ config_name: configName });
  await runStart(run.id as number);
}
