import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { stateApi, type StateRun } from '../../api';
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

export function RunsPage() {
  const { showError } = useToast();
  const { t } = useI18n();
  const [current, setCurrent] = useState<StateRun | null>(null);
  const [archive, setArchive] = useState<StateRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<{ run: StateRun; archive: boolean } | null>(null);
  const hasDataRef = useRef(false);

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

  const load = useCallback(async () => {
    if (!hasDataRef.current) setLoading(true);
    try {
      const data = (await stateApi.runs('all')) as {
        current_run?: StateRun | null;
        items?: StateRun[];
      };
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
      setCurrent(cur);
      setArchive(rest);
      hasDataRef.current = Boolean(cur) || rest.length > 0;
    } catch (e) {
      showError(e instanceof Error ? e.message : t('runs.loadError'));
    } finally {
      setLoading(false);
    }
  }, [showError, t]);

  useEffect(() => {
    void load();
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
