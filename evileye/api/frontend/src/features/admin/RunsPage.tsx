import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  journalsApi,
  stateApi,
  type StateRun,
  cacheGet,
  cacheSet,
  isAbortError,
} from '../../api';
import { Badge, Button, Modal } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useAuth } from '../../auth/AuthContext';
import { useI18n } from '../../i18n';
import {
  configStudioHref,
  inferConfigNameFromJob,
  logFileHref,
  matchRunConfig,
  runConfigName,
  runMainLogFile,
} from './runLinks';

function statusLabel(state: string | undefined, t: (key: string) => string): string {
  const raw = String(state || '').trim() || 'unknown';
  const key = `runs.state.${raw}`;
  const translated = t(key);
  return translated === key ? raw : translated;
}

function archiveStatusLabel(state: string | undefined, t: (key: string) => string): string {
  return String(state || '').trim() === 'error' ? t('runs.state.error') : t('runs.state.stopped');
}

function archiveBadgeState(state: string | undefined): string {
  return String(state || '').trim() === 'error' ? 'error' : 'stopped';
}

const RUNS_CACHE_KEY = 'state:runs:all';
const RUNS_TTL_MS = 15_000;

type RunsPayload = { current_run?: StateRun | null; items?: StateRun[] };

function splitRuns(data: RunsPayload): { cur: StateRun | null; rest: StateRun[] } {
  const cur = data.current_run ?? null;
  const items = data.items ?? [];
  const curId = cur?.id;
  const rest = items
    .filter((r) => curId == null || r.id !== curId)
    .sort((a, b) => {
      const ua = Number(a.updated_at ?? 0);
      const ub = Number(b.updated_at ?? 0);
      if (ub !== ua) return ub - ua;
      return Number(b.id ?? 0) - Number(a.id ?? 0);
    });
  return { cur, rest };
}

export function RunsPage() {
  const { showError } = useToast();
  const { t, formatDateTime } = useI18n();
  const { hasPermission } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const configFilter = searchParams.get('config');
  const highlightRaw = searchParams.get('highlight');
  const highlightId = highlightRaw != null && highlightRaw !== '' ? Number(highlightRaw) : null;

  const cached = cacheGet<RunsPayload>(RUNS_CACHE_KEY);
  const initial = cached ? splitRuns(cached) : null;
  const [current, setCurrent] = useState<StateRun | null>(() => initial?.cur ?? null);
  const [archive, setArchive] = useState<StateRun[]>(() => initial?.rest ?? []);
  const [loading, setLoading] = useState(() => !initial);
  const [detail, setDetail] = useState<{ run: StateRun; archive: boolean } | null>(null);
  const hasDataRef = useRef(Boolean(initial));
  const highlightRef = useRef<HTMLTableRowElement | null>(null);

  const canViewConfig = hasPermission('config:view');
  const canViewLogs = hasPermission('logs:view');
  const canViewHistory = hasPermission('history:view');

  const [dbItems, setDbItems] = useState<Record<string, unknown>[]>([]);
  const [dbAvailable, setDbAvailable] = useState<boolean | null>(null);
  const [dbMessage, setDbMessage] = useState<string | null>(null);
  const [dbLoading, setDbLoading] = useState(false);

  const formatUptime = (sec: number | null | undefined): string => {
    if (sec == null || Number.isNaN(sec)) return '—';
    const s = Math.floor(sec);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const r = s % 60;
    if (h > 0) return t('runs.uptime.h', { h, m });
    if (m > 0) return t('runs.uptime.m', { m, s: r });
    return t('runs.uptime.s', { s: r });
  };

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!hasDataRef.current) setLoading(true);
      try {
        const data = (await stateApi.runs('all', { signal })) as RunsPayload;
        if (signal?.aborted) return;
        cacheSet(RUNS_CACHE_KEY, data, RUNS_TTL_MS);
        const { cur, rest } = splitRuns(data);
        setCurrent(cur);
        setArchive(rest);
        hasDataRef.current = Boolean(cur) || rest.length > 0;
      } catch (e) {
        if (isAbortError(e) || signal?.aborted) return;
        showError(e instanceof Error ? e.message : t('runs.loadError'));
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [showError],
  );

  const loadDbHistory = useCallback(
    async (signal?: AbortSignal) => {
      if (!canViewHistory) return;
      setDbLoading(true);
      try {
        const res = await journalsApi.configHistory(30, { signal });
        if (signal?.aborted) return;
        setDbAvailable(Boolean(res.available));
        setDbItems(res.items ?? []);
        setDbMessage(res.message ?? null);
      } catch (e) {
        if (isAbortError(e) || signal?.aborted) return;
        setDbAvailable(false);
        setDbItems([]);
        setDbMessage(e instanceof Error ? e.message : t('runs.dbHistoryUnavailable'));
      } finally {
        if (!signal?.aborted) setDbLoading(false);
      }
    },
    [canViewHistory],
  );

  useEffect(() => {
    const ac = new AbortController();
    void load(ac.signal);
    return () => ac.abort();
  }, [load]);

  useEffect(() => {
    if (!canViewHistory) return;
    const ac = new AbortController();
    void loadDbHistory(ac.signal);
    return () => ac.abort();
  }, [canViewHistory, loadDbHistory]);

  useEffect(() => {
    if (highlightId == null || Number.isNaN(highlightId)) return;
    const timer = window.setTimeout(() => {
      highlightRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 100);
    return () => window.clearTimeout(timer);
  }, [highlightId, current, archive]);

  const filteredArchive = useMemo(
    () => archive.filter((r) => matchRunConfig(r, configFilter)),
    [archive, configFilter],
  );

  const clearConfigFilter = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('config');
    setSearchParams(next, { replace: true });
  };

  const renderConfigCell = (r: StateRun): ReactNode => {
    const name = runConfigName(r);
    if (!name) return '—';
    if (canViewConfig) {
      return (
        <Link className="run-config-link" to={configStudioHref(name)} title={r.config_path ?? name}>
          {name}
        </Link>
      );
    }
    return (
      <span className="run-config" title={r.config_path ?? name}>
        {name}
      </span>
    );
  };

  const renderLogCell = (r: StateRun): ReactNode => {
    const main = runMainLogFile(r);
    const heuristic = r.log_match === 'heuristic';
    if (canViewLogs && main) {
      return (
        <Link
          className="btn btn-sm btn-outline"
          to={logFileHref(main)}
          title={heuristic ? t('runs.logHeuristic') : main}
        >
          {t('runs.openLog')}
          {heuristic ? '≈' : ''}
        </Link>
      );
    }
    return (
      <Button size="sm" variant="outline" disabled title={t('runs.noLog')}>
        {t('runs.noLog')}
      </Button>
    );
  };

  const renderTable = (rows: StateRun[], opts: { archive: boolean; markCurrent?: boolean }): ReactNode => (
    <table className="journal-table">
      <thead>
        <tr>
          <th>{t('runs.columns.id')}</th>
          <th>{t('runs.columns.name')}</th>
          <th>{t('runs.columns.status')}</th>
          <th>{t('runs.columns.config')}</th>
          <th>{t('runs.columns.log')}</th>
          <th>{t('runs.columns.pipeline')}</th>
          <th>{t('runs.columns.pid')}</th>
          <th>{t('runs.columns.uptime')}</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const highlighted = highlightId != null && r.id === highlightId;
          const configMatch = configFilter ? matchRunConfig(r, configFilter) : false;
          return (
            <tr
              key={r.id}
              ref={highlighted ? highlightRef : undefined}
              className={[highlighted ? 'run-row-highlight' : '', configMatch && !opts.archive ? 'run-row-config-match' : '']
                .filter(Boolean)
                .join(' ') || undefined}
            >
              <td>#{r.id}</td>
              <td>{r.name ?? '—'}</td>
              <td>
                <div className="runs-status-cell">
                  {opts.archive ? (
                    <Badge state={archiveBadgeState(r.state)}>{archiveStatusLabel(r.state, t)}</Badge>
                  ) : (
                    <>
                      <Badge state={r.state}>{statusLabel(r.state, t)}</Badge>
                      {opts.markCurrent ? <Badge state="running">{t('runs.current')}</Badge> : null}
                    </>
                  )}
                </div>
              </td>
              <td className="run-config">{renderConfigCell(r)}</td>
              <td>{renderLogCell(r)}</td>
              <td>{r.pipeline_class ?? '—'}</td>
              <td>{r.pid ?? '—'}</td>
              <td>{formatUptime(r.uptime_seconds)}</td>
              <td>
                <Button size="sm" variant="outline" onClick={() => setDetail({ run: r, archive: opts.archive })}>
                  {t('runs.view')}
                </Button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );

  const detailStatus = detail
    ? detail.archive
      ? archiveStatusLabel(detail.run.state, t)
      : statusLabel(detail.run.state, t)
    : '';

  const detailConfigName = detail ? runConfigName(detail.run) : null;
  const detailLogs = detail?.run.log_files;

  return (
    <section className="panel active">
      <div className="card runs-card">
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>{t('runs.title')}</h2>
          <Button
            variant="outline"
            onClick={() => {
              void load();
              void loadDbHistory();
            }}
          >
            {t('runs.refresh')}
          </Button>
        </div>
        <p className="hint">{t('runs.hint')}</p>

        {configFilter ? (
          <div className="setup-banner" style={{ marginBottom: '0.75rem' }}>
            <span>{t('runs.filterByConfig', { name: configFilter })}</span>
            <Button size="sm" variant="outline" onClick={clearConfigFilter}>
              {t('runs.clearFilter')}
            </Button>
          </div>
        ) : null}

        <div className="runs-section">
          <h3 className="runs-section-title">{t('runs.activeTitle')}</h3>
          {loading && !current ? (
            <p className="empty">{t('common.searching')}</p>
          ) : !current ? (
            <p className="empty">{t('runs.activeEmpty')}</p>
          ) : (
            renderTable([current], { archive: false, markCurrent: true })
          )}
        </div>

        <div className="runs-section">
          <h3 className="runs-section-title">{t('runs.archiveTitle')}</h3>
          {loading && !filteredArchive.length ? (
            <p className="empty">{t('common.searching')}</p>
          ) : !filteredArchive.length ? (
            <p className="empty">{t('runs.archiveEmpty')}</p>
          ) : (
            renderTable(filteredArchive, { archive: true })
          )}
        </div>

        {canViewHistory ? (
          <div className="runs-section">
            <h3 className="runs-section-title">{t('runs.dbHistoryTitle')}</h3>
            {dbLoading && dbAvailable == null ? (
              <p className="empty">{t('common.searching')}</p>
            ) : dbAvailable === false ? (
              <p className="hint">{dbMessage || t('runs.dbHistoryUnavailable')}</p>
            ) : !dbItems.length ? (
              <p className="empty">{t('runs.dbHistoryEmpty')}</p>
            ) : (
              <table className="journal-table">
                <thead>
                  <tr>
                    <th>{t('journals.colJob')}</th>
                    <th>{t('journals.colProject')}</th>
                    <th>{t('journals.colConfig')}</th>
                    <th>{t('journals.colStatus')}</th>
                    <th>{t('journals.colCreated')}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {dbItems.map((item) => {
                    const jobId = item.job_id as number | undefined;
                    const inferred = inferConfigNameFromJob(item) || configFilter;
                    const created = item.creation_time;
                    const createdLabel =
                      created != null ? formatDateTime(created as string | number) : '—';
                    return (
                      <tr key={String(jobId ?? `${item.project_id}-${item.creation_time}`)}>
                        <td>#{jobId ?? '—'}</td>
                        <td>{item.project_id != null ? String(item.project_id) : '—'}</td>
                        <td>{item.configuration_id != null ? String(item.configuration_id) : '—'}</td>
                        <td>{String(item.status ?? '—')}</td>
                        <td>{createdLabel}</td>
                        <td>
                          {canViewConfig && inferred ? (
                            <Link className="btn btn-sm btn-outline" to={configStudioHref(inferred, 'history')}>
                              {t('runs.openInStudioHistory')}
                            </Link>
                          ) : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        ) : null}
      </div>
      <Modal open={Boolean(detail)} title={t('runs.detail')} onClose={() => setDetail(null)}>
        {detail ? (
          <>
            <p>
              <strong>{t('runs.columns.id')}</strong> {detail.run.id}
            </p>
            <p>
              <strong>{t('runs.columns.name')}</strong> {detail.run.name ?? '—'}
            </p>
            <p>
              <strong>{t('runs.columns.status')}</strong> {detailStatus}
            </p>
            <p>
              <strong>{t('runs.columns.config')}</strong>{' '}
              {detailConfigName && canViewConfig ? (
                <Link to={configStudioHref(detailConfigName)}>{detailConfigName}</Link>
              ) : (
                detail.run.config_path ?? '—'
              )}
            </p>
            {detail.run.config_path ? (
              <p className="hint" style={{ marginTop: 0 }}>
                {detail.run.config_path}
              </p>
            ) : null}
            <p>
              <strong>{t('runs.columns.pipeline')}</strong> {detail.run.pipeline_class ?? '—'}
            </p>
            <p>
              <strong>{t('runs.columns.pid')}</strong> {detail.run.pid ?? '—'}
            </p>
            <p>
              <strong>{t('runs.columns.uptime')}</strong> {formatUptime(detail.run.uptime_seconds)}
            </p>
            <p>
              <strong>log_session_id</strong> {detail.run.log_session_id ?? '—'}
              {detail.run.log_match ? ` (${detail.run.log_match})` : ''}
            </p>
            {canViewLogs && detailLogs ? (
              <div className="runs-log-links">
                <strong>{t('runs.columns.log')}</strong>
                <ul>
                  {detailLogs.main ? (
                    <li>
                      <Link to={logFileHref(detailLogs.main)}>{detailLogs.main}</Link>
                    </li>
                  ) : null}
                  {detailLogs.errors ? (
                    <li>
                      <Link to={logFileHref(detailLogs.errors)}>{detailLogs.errors}</Link>
                    </li>
                  ) : null}
                  {detailLogs.performance ? (
                    <li>
                      <Link to={logFileHref(detailLogs.performance)}>{detailLogs.performance}</Link>
                    </li>
                  ) : null}
                  {!detailLogs.main && !detailLogs.errors && !detailLogs.performance ? (
                    <li>{t('runs.noLog')}</li>
                  ) : null}
                </ul>
              </div>
            ) : null}
            {detail.run.error ? <p className="run-error">{detail.run.error}</p> : null}
          </>
        ) : null}
      </Modal>
    </section>
  );
}
