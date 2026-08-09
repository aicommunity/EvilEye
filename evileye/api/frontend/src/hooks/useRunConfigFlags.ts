import { useEffect, useState } from 'react';
import { setupApi, stateApi, isAbortError } from '../api';
import { configBasename } from '../features/configure/studioTabs';

export type RunConfigFlags = {
  loading: boolean;
  configName: string | null;
  recordingEnabled: boolean | null;
  analyticsEnabled: boolean | null;
};

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
          const items = Array.isArray(res) ? res : res.items ?? [];
          const running = items.find((r) => r.state === 'running') ?? items[0];
          name = configBasename(running?.config_path) ?? undefined;
        } catch (e) {
          if (isAbortError(e)) return;
        }
        const st = await setupApi.status(name);
        if (ac.signal.aborted) return;
        setConfigName(st.default_config || name || null);
        setRecordingEnabled(Boolean(st.recording_enabled));
        setAnalyticsEnabled(Boolean(st.analytics_enabled));
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
