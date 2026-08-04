import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { stateApi, type OverviewResponse, type StateCamera } from '../../api';
import { Badge, Button, MetricCard } from '../../components/ui';
import { StreamOverlay } from '../../components/StreamOverlay';
import { usePolling } from '../../hooks/usePolling';
import { streamSnapshotUrl } from '../../api';

export function OverviewPage() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [stream, setStream] = useState<{ rid: number; sid: number | null } | null>(null);

  const load = useCallback(async () => {
    setData(await stateApi.overview());
  }, []);

  usePolling(load, 8000);

  const stats = data?.server.journal_stats;
  const cameras = data?.cameras ?? [];

  return (
    <section className="panel active">
      <div className="card">
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>Обзор сервера</h2>
          <Button variant="outline" onClick={() => void load()}>
            Обновить
          </Button>
        </div>
        <div className="metric-grid">
          <MetricCard label="Статус" value={data?.server.status ?? '—'} />
          <MetricCard label="Активные запуски" value={data?.server.active_runs_total ?? '—'} />
          <MetricCard label="Камеры" value={data?.server.cameras_total ?? '—'} />
          <MetricCard label="Web preview" value={data?.server.web_previews_available ?? '—'} />
          <MetricCard label="События" value={stats?.available ? String(stats.events_total ?? 0) : 'БД недоступна'} />
          <MetricCard label="Объекты" value={stats?.available ? String(stats.objects_total ?? 0) : '—'} />
        </div>
        <h3 className="section-title">Текущий запуск</h3>
        {!data?.current_run ? (
          <p className="empty">Нет активного запуска.</p>
        ) : (
          <div className="overview-run-detail">
            <p>
              <strong>{data.current_run.name ?? `Запуск ${data.current_run.id}`}</strong> #{data.current_run.id}{' '}
              <Badge state={data.current_run.state}>{data.current_run.state}</Badge>
            </p>
            <p className="hint">
              {data.current_run.pipeline_class ?? 'pipeline n/a'} · PID {data.current_run.pid ?? '—'}
            </p>
            <Link className="btn btn-sm btn-outline" to="/admin/runs">
              К запускам
            </Link>
          </div>
        )}
        <h3 className="section-title">Камеры</h3>
        <div className="camera-group-grid">
          {cameras.map((c: StateCamera) => (
            <article key={`${c.run_id}:${c.source_id}`} className="camera-card camera-card-mini">
              <div className="camera-card-head">
                <span className="run-name">{c.source_name}</span>
                <Badge state={c.run_state}>{c.run_state}</Badge>
              </div>
              {c.run_state === 'running' ? (
                <img
                  className="camera-preview"
                  src={`${streamSnapshotUrl(c.run_id, c.source_id)}${streamSnapshotUrl(c.run_id, c.source_id).includes('?') ? '&' : '?'}t=${data?.timestamp ?? 0}`}
                  alt={c.source_name}
                />
              ) : (
                <div className="camera-preview camera-preview-empty">Остановлен</div>
              )}
              <Button size="sm" variant="outline" disabled={c.run_state !== 'running'} onClick={() => setStream({ rid: c.run_id, sid: c.source_id })}>
                Открыть поток
              </Button>
            </article>
          ))}
        </div>
      </div>
      {stream ? <StreamOverlay rid={stream.rid} sourceId={stream.sid} onClose={() => setStream(null)} /> : null}
    </section>
  );
}
