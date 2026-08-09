import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { stateApi, type StateRun, cacheGet, cacheSet, isAbortError } from '../../api';
import { Badge, Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useAuth } from '../../auth/AuthContext';
import { useI18n } from '../../i18n';
import { logFileHref, matchRunConfig, runMainLogFile, runsHubHref } from '../admin/runLinks';

const RUNS_CACHE_KEY = 'state:runs:all';
const RUNS_TTL_MS = 15_000;

type RunsPayload = { current_run?: StateRun | null; items?: StateRun[] };

function statusLabel(state: string | undefined, t: (key: string) => string): string {
  const raw = String(state || '').trim() || 'unknown';
  const key = `runs.state.${raw}`;
  const translated = t(key);
  return translated === key ? raw : translated;
}

export function ConfigRelatedRunsPanel({ configName }: { configName: string }) {
  const { t } = useI18n();
  const { showError } = useToast();
  const { hasPermission } = useAuth();
  const canViewLogs = hasPermission('logs:view');
  const canViewRuntime = hasPermission('runtime:view');

  const cached = cacheGet<RunsPayload>(RUNS_CACHE_KEY);
  const [items, setItems] = useState<StateRun[]>(() => {
    if (!cached) return [];
    const all = [...(cached.items ?? [])];
    if (cached.current_run && !all.some((r) => r.id === cached.current_run!.id)) {
      all.unshift(cached.current_run);
    }
    return all.filter((r) => matchRunConfig(r, configName));
  });
  const [loading, setLoading] = useState(() => !cached);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!canViewRuntime) return;
      try {
        const data = (await stateApi.runs('all', { signal })) as RunsPayload;
        if (signal?.aborted) return;
        cacheSet(RUNS_CACHE_KEY, data, RUNS_TTL_MS);
        const all = [...(data.items ?? [])];
        if (data.current_run && !all.some((r) => r.id === data.current_run!.id)) {
          all.unshift(data.current_run);
        }
        setItems(all.filter((r) => matchRunConfig(r, configName)));
      } catch (e) {
        if (isAbortError(e) || signal?.aborted) return;
        showError(e instanceof Error ? e.message : t('runs.loadError'));
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [canViewRuntime, configName, showError, t],
  );

  useEffect(() => {
    if (!canViewRuntime) {
      setLoading(false);
      return;
    }
    const ac = new AbortController();
    void load(ac.signal);
    return () => ac.abort();
  }, [canViewRuntime, load]);

  const sorted = useMemo(
    () =>
      [...items].sort((a, b) => {
        const ua = Number(a.updated_at ?? 0);
        const ub = Number(b.updated_at ?? 0);
        return ub - ua;
      }),
    [items],
  );

  if (!canViewRuntime) return null;

  return (
    <div className="config-related-runs">
      <h3 className="config-related-runs-title">{t('configs.relatedRunsTitle')}</h3>
      {loading && !sorted.length ? (
        <p className="empty">{t('common.searching')}</p>
      ) : !sorted.length ? (
        <p className="empty">{t('configs.relatedRunsEmpty')}</p>
      ) : (
        <table className="journal-table">
          <thead>
            <tr>
              <th>{t('runs.columns.id')}</th>
              <th>{t('runs.columns.status')}</th>
              <th>{t('runs.columns.uptime')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, 10).map((r) => {
              const main = runMainLogFile(r);
              return (
                <tr key={r.id}>
                  <td>#{r.id}</td>
                  <td>
                    <Badge state={r.state}>{statusLabel(r.state, t)}</Badge>
                  </td>
                  <td>
                    {r.uptime_seconds != null && !Number.isNaN(r.uptime_seconds)
                      ? `${Math.floor(r.uptime_seconds)}s`
                      : '—'}
                  </td>
                  <td>
                    <div className="run-actions">
                      <Link
                        className="btn btn-sm btn-outline"
                        to={runsHubHref({ config: configName, highlight: r.id })}
                      >
                        {t('runs.view')}
                      </Link>
                      {canViewLogs && main ? (
                        <Link className="btn btn-sm btn-outline" to={logFileHref(main)}>
                          {t('runs.openLog')}
                        </Link>
                      ) : (
                        <Button size="sm" variant="outline" disabled>
                          {t('runs.noLog')}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {sorted.length > 0 ? (
        <p className="hint" style={{ marginTop: '0.5rem', marginBottom: 0 }}>
          <Link to={runsHubHref({ config: configName })}>
            {t('configs.relatedRunsCount', { count: sorted.length })}
          </Link>
        </p>
      ) : null}
    </div>
  );
}
