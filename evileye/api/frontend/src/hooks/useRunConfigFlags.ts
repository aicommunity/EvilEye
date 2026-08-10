import { useEffect, useState } from 'react';
import { setupApi, stateApi, isAbortError, type StateRun } from '../api';
import { configBasename } from '../features/configure/studioTabs';

export type RunConfigFlags = {
  loading: boolean;
  configName: string | null;
  recordingEnabled: boolean | null;
  analyticsEnabled: boolean | null;
};

function pickCurrentRun(res: { current_run?: StateRun | null; items?: StateRun[] } | StateRun[]): StateRun | null {
  if (Array.isArray(res)) {
    return res.find((r) => r.state === 'running') ?? res[0] ?? null;
  }
  if (res.current_run) return res.current_run;
  const items = res.items ?? [];
  return items.find((r) => r.state === 'running') ?? items[0] ?? null;
}

/**
 * Flags from the current run's config (falls back to default setup status).
 */
export function useRunConfigFlags(): RunConfigFlags {
  const [loading, setLoading] = useState(true);
  const [configName, setConfigName] = useState<string | null>(null);
  const [recordingEnabled, setRecordingEnabled] = useState<boolean | null>(null);
  const [analyticsEnabled, setAnalyticsEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    void (async () => {
      setLoading(true);
      try {
        let name: string | undefined;
        try {
          const res = await stateApi.runs('current', { signal: ac.signal });
          if (ac.signal.aborted) return;
          const running = pickCurrentRun(res);
          name = configBasename(running?.config_path) ?? undefined;
        } catch (e) {
          if (isAbortError(e)) return;
        }
        // Prefer basic projection: recording_enabled already accounts for enabled_sources.
        const [st, basic] = await Promise.all([
          setupApi.status(name),
          setupApi.basicGet(name).catch(() => null),
        ]);
        if (ac.signal.aborted) return;
        const resolvedName = (basic?.config_name || name || st.default_config || null) as string | null;
        setConfigName(resolvedName);
        const recording =
          basic != null ? Boolean(basic.recording_enabled) : Boolean(st.recording_enabled);
        setRecordingEnabled(recording);
        setAnalyticsEnabled(
          basic != null ? Boolean(basic.analytics_enabled) : Boolean(st.analytics_enabled),
        );
      } catch (e) {
        if (isAbortError(e)) return;
        setRecordingEnabled(null);
        setAnalyticsEnabled(null);
      } finally {
        if (!ac.signal.aborted) setLoading(false);
      }
    })();
    return () => ac.abort();
  }, []);

  return { loading, configName, recordingEnabled, analyticsEnabled };
}
