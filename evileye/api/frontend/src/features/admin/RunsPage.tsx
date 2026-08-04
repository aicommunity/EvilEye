import { useCallback, useEffect, useState } from 'react';
import { stateApi, type StateRun } from '../../api';
import { Badge, Button, Modal } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';

function formatUptime(sec: number | null | undefined): string {
  if (sec == null || Number.isNaN(sec)) return '—';
  const s = Math.floor(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h > 0) return `${h}ч ${m}м`;
  if (m > 0) return `${m}м ${r}с`;
  return `${r}с`;
}

export function RunsPage() {
  const { showError } = useToast();
  const { t } = useI18n();
  const [items, setItems] = useState<StateRun[]>([]);
  const [current, setCurrent] = useState<StateRun | null>(null);
  const [detail, setDetail] = useState<StateRun | null>(null);

  const load = useCallback(async () => {
    try {
      const data = (await stateApi.runs('active')) as {
        current_run?: StateRun | null;
        items?: StateRun[];
      };
      setCurrent(data.current_run ?? null);
      setItems(data.items ?? []);
    } catch (e) {
      showError(e instanceof Error ? e.message : t('runs.loadError'));
    }
  }, [showError]);

  useEffect(() => {
    void load();
  }, [load]);

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
        {!items.length && !current ? (
          <p className="empty">{t('runs.empty')}</p>
        ) : (
          <table className="journal-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Имя</th>
                <th>Статус</th>
                <th>Конфиг</th>
                <th>Pipeline</th>
                <th>PID</th>
                <th>Uptime</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(items.length ? items : current ? [current] : []).map((r) => (
                <tr key={r.id}>
                  <td>#{r.id}</td>
                  <td>{r.name ?? '—'}</td>
                  <td>
                    <Badge state={r.state}>{r.state}</Badge>
                    {current?.id === r.id ? <span className="config-active-badge"> {t('runs.current')}</span> : null}
                  </td>
                  <td className="run-config">{r.config_path ?? '—'}</td>
                  <td>{r.pipeline_class ?? '—'}</td>
                  <td>{r.pid ?? '—'}</td>
                  <td>{formatUptime(r.uptime_seconds)}</td>
                  <td>
                    <Button size="sm" variant="outline" onClick={() => setDetail(r)}>
                      {t('runs.view')}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <Modal open={Boolean(detail)} title={t('runs.detail')} onClose={() => setDetail(null)}>
        {detail ? (
          <>
            <p>
              <strong>ID</strong> {detail.id}
            </p>
            <p>
              <strong>Имя</strong> {detail.name ?? '—'}
            </p>
            <p>
              <strong>Статус</strong> {detail.state}
            </p>
            <p>
              <strong>Конфиг</strong> {detail.config_path}
            </p>
            <p>
              <strong>Pipeline</strong> {detail.pipeline_class ?? '—'}
            </p>
            <p>
              <strong>PID</strong> {detail.pid ?? '—'}
            </p>
            <p>
              <strong>Uptime</strong> {formatUptime(detail.uptime_seconds)}
            </p>
            {detail.error ? <p className="run-error">{detail.error}</p> : null}
          </>
        ) : null}
      </Modal>
    </section>
  );
}
