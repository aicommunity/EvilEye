import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { stateApi, type StateRun, cacheGet, cacheSet, isAbortError } from '../../api';
import { Badge, Button, Modal } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';

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
  const { t } = useI18n();
  const cached = cacheGet<RunsPayload>(RUNS_CACHE_KEY);
  const initial = cached ? splitRuns(cached) : null;
  const [current, setCurrent] = useState<StateRun | null>(() => initial?.cur ?? null);
  const [archive, setArchive] = useState<StateRun[]>(() => initial?.rest ?? []);
  const [loading, setLoading] = useState(() => !initial);
  const [detail, setDetail] = useState<{ run: StateRun; archive: boolean } | null>(null);
  const hasDataRef = useRef(Boolean(initial));

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
    [showError, t],
  );

  useEffect(() => {
    const ac = new AbortController();
    void load(ac.signal);
    return () => ac.abort();
  }, [load]);

  const renderTable = (rows: StateRun[], opts: { archive: boolean; markCurrent?: boolean }): ReactNode => (
    <table className="journal-table">
      <thead>
        <tr>
          <th>{t('runs.columns.id')}</th>
          <th>{t('runs.columns.name')}</th>
          <th>{t('runs.columns.status')}</th>
          <th>{t('runs.columns.config')}</th>
          <th>{t('runs.columns.pipeline')}</th>
          <th>{t('runs.columns.pid')}</th>
          <th>{t('runs.columns.uptime')}</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id}>
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
            <td className="run-config">{r.config_path ?? '—'}</td>
            <td>{r.pipeline_class ?? '—'}</td>
            <td>{r.pid ?? '—'}</td>
            <td>{formatUptime(r.uptime_seconds)}</td>
            <td>
              <Button size="sm" variant="outline" onClick={() => setDetail({ run: r, archive: opts.archive })}>
                {t('runs.view')}
              </Button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  const detailStatus = detail
    ? detail.archive
      ? archiveStatusLabel(detail.run.state, t)
      : statusLabel(detail.run.state, t)
    : '';

  return (
    <section className="panel active">
      <div className="card runs-card">
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>{t('runs.title')}</h2>
          <Button variant="outline" onClick={() => void load()}>
            {t('runs.refresh')}
          </Button>
        </div>
        <p className="hint">{t('runs.hint')}</p>

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
          {loading && !archive.length ? (
            <p className="empty">{t('common.searching')}</p>
          ) : !archive.length ? (
            <p className="empty">{t('runs.archiveEmpty')}</p>
          ) : (
            renderTable(archive, { archive: true })
          )}
        </div>
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
              <strong>{t('runs.columns.config')}</strong> {detail.run.config_path}
            </p>
            <p>
              <strong>{t('runs.columns.pipeline')}</strong> {detail.run.pipeline_class ?? '—'}
            </p>
            <p>
              <strong>{t('runs.columns.pid')}</strong> {detail.run.pid ?? '—'}
            </p>
            <p>
              <strong>{t('runs.columns.uptime')}</strong> {formatUptime(detail.run.uptime_seconds)}
            </p>
            {detail.run.error ? <p className="run-error">{detail.run.error}</p> : null}
          </>
        ) : null}
      </Modal>
    </section>
  );
}
