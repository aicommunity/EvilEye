import { useCallback, useMemo, useState } from 'react';
import { stateApi, journalsApi, type StateCamera, type StreamMetadata } from '../../api';
import { Button, Badge } from '../../components/ui';
import { StreamOverlay } from '../../components/StreamOverlay';
import { usePolling } from '../../hooks/usePolling';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api';
import { CameraGrid } from './CameraGrid';
import { LiveAlertsRail } from './LiveAlertsRail';
import { useLiveLayout } from './useLiveLayout';

export function LivePage() {
  const { showError } = useToast();
  const [cameras, setCameras] = useState<StateCamera[]>([]);
  const [stats, setStats] = useState<{ events?: number; objects?: number }>({});
  const [stream, setStream] = useState<{ rid: number; sid: number | null } | null>(null);
  const { cols, setCols, order, setOrder } = useLiveLayout();

  const load = useCallback(async () => {
    try {
      const [camRes, st] = await Promise.all([stateApi.cameras('current'), journalsApi.stats().catch(() => null)]);
      setCameras(camRes.items ?? []);
      if (st?.available) setStats({ events: st.events_total, objects: st.objects_total });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return;
      showError(e instanceof Error ? e.message : 'Не удалось загрузить камеры');
    }
  }, [showError]);

  usePolling(load, 5000);

  const ordered = useMemo(() => {
    if (!order.length) return cameras;
    const map = new Map(cameras.map((c) => [`${c.run_id}:${c.source_id}`, c]));
    const result: StateCamera[] = [];
    for (const key of order) {
      const cam = map.get(key);
      if (cam) {
        result.push(cam);
        map.delete(key);
      }
    }
    for (const cam of map.values()) result.push(cam);
    return result;
  }, [cameras, order]);

  return (
    <section className="panel active">
      <div className="card">
        <div className="toolbar" style={{ justifyContent: 'space-between' }}>
          <div>
            <h2 style={{ margin: 0 }}>Live</h2>
            <p className="hint">Сетка камер текущего запуска</p>
          </div>
          <div className="toolbar">
            {[1, 4, 9, 16].map((n) => (
              <Button key={n} size="sm" variant={cols === Math.sqrt(n) || (n === 1 && cols === 1) ? 'primary' : 'outline'} onClick={() => setCols(n === 1 ? 1 : Math.round(Math.sqrt(n)))}>
                {n}
              </Button>
            ))}
            <Button variant="outline" onClick={() => void load()}>
              Обновить
            </Button>
          </div>
        </div>
        <LiveAlertsRail eventsTotal={stats.events} objectsTotal={stats.objects} cameras={cameras.length} />
        <CameraGrid
          cameras={ordered}
          cols={cols}
          onOpenStream={(rid, sid) => setStream({ rid, sid })}
          onReorder={setOrder}
        />
      </div>
      {stream ? (
        <StreamOverlay rid={stream.rid} sourceId={stream.sid} onClose={() => setStream(null)} />
      ) : null}
    </section>
  );
}

export type { StreamMetadata };
