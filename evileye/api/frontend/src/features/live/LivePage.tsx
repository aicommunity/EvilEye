import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { stateApi, journalsApi, streamStatus, type StateCamera } from '../../api';
import { Button } from '../../components/ui';
import { StreamOverlay } from '../../components/StreamOverlay';
import { useVisibilityPolling } from '../../hooks/useVisibilityPolling';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api';
import { useI18n } from '../../i18n';
import { CameraGrid } from './CameraGrid';
import { ExpandedCameraView } from './ExpandedCameraView';
import { LiveAlertsRail } from './LiveAlertsRail';
import { useLiveLayout } from './useLiveLayout';
import { useLiveGridPreviewWs } from './useLiveGridPreviewWs';
import { fitColsForCount } from '../layout/fitGrid';

export function LivePage() {
  const { showError } = useToast();
  const { t } = useI18n();
  const [cameras, setCameras] = useState<StateCamera[]>([]);
  const [camerasLoading, setCamerasLoading] = useState(true);
  const camerasRef = useRef(cameras);
  camerasRef.current = cameras;
  const [stats, setStats] = useState<{ events?: number; objects?: number }>({});
  const [stream, setStream] = useState<{ rid: number; sid: number | null } | null>(null);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const { cols, setCols, order, setOrder, mode, setMode } = useLiveLayout();

  const load = useCallback(async () => {
    if (!camerasRef.current.length) setCamerasLoading(true);
    try {
      const [camRes, st] = await Promise.all([stateApi.cameras('current'), journalsApi.stats().catch(() => null)]);
      setCameras(camRes.items ?? []);
      if (st?.available) setStats({ events: st.events_total, objects: st.objects_total });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return;
      showError(e instanceof Error ? e.message : t('live.empty'));
    } finally {
      setCamerasLoading(false);
    }
  }, [showError, t]);

  useVisibilityPolling(load, 5000, true, 0);

  const primaryRunId = useMemo(() => {
    const ids = [...new Set(cameras.map((c) => c.run_id).filter((id) => Number.isFinite(id)))];
    return ids.length === 1 ? ids[0] : ids[0] ?? null;
  }, [cameras]);

  const previewSourceIds = useMemo(
    () => cameras.map((c) => c.source_id).filter((id): id is number => id != null),
    [cameras],
  );

  const previewWs = useLiveGridPreviewWs(primaryRunId, previewSourceIds);

  // Keep preview demand warm while Live is open. Skip only the run already covered by grid WS.
  useEffect(() => {
    const runIds = [...new Set(cameras.map((c) => c.run_id).filter((id) => Number.isFinite(id)))];
    if (!runIds.length) return;

    const tick = () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      for (const rid of runIds) {
        if (previewWs.connected && primaryRunId != null && rid === primaryRunId) continue;
        void streamStatus(rid).catch(() => undefined);
      }
    };
    tick();
    const id = window.setInterval(tick, 15000);
    return () => window.clearInterval(id);
  }, [cameras, previewWs.connected, primaryRunId]);

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

  const expandedCamera = useMemo(() => {
    if (!expandedKey) return null;
    return ordered.find((c) => `${c.run_id}:${c.source_id}` === expandedKey) ?? null;
  }, [expandedKey, ordered]);

  useEffect(() => {
    if (!expandedKey) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExpandedKey(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [expandedKey]);

  const effectiveCols = mode === 'fit' ? fitColsForCount(ordered.length) : cols;

  return (
    <section className={`panel active${mode === 'fit' ? ' live-page--fit' : ''}`}>
      <div className={`card${mode === 'fit' ? ' live-page-card' : ''}`}>
        <div className="toolbar" style={{ justifyContent: 'space-between' }}>
          <div>
            <h2 style={{ margin: 0 }}>{t('live.title')}</h2>
            <p className="hint">{t('live.hint')}</p>
          </div>
          <div className="toolbar">
            <Button size="sm" variant={mode === 'fit' ? 'primary' : 'outline'} onClick={() => setMode('fit')}>
              {t('layout.fit')}
            </Button>
            <Button size="sm" variant={mode === 'fixed' ? 'primary' : 'outline'} onClick={() => setMode('fixed')}>
              {t('layout.fixed')}
            </Button>
            {mode === 'fixed'
              ? [1, 4, 9, 16].map((n) => (
                  <Button
                    key={n}
                    size="sm"
                    variant={cols === Math.sqrt(n) || (n === 1 && cols === 1) ? 'primary' : 'outline'}
                    onClick={() => setCols(n === 1 ? 1 : Math.round(Math.sqrt(n)))}
                  >
                    {n}
                  </Button>
                ))
              : null}
            <Button variant="outline" onClick={() => void load()}>
              {t('live.refresh')}
            </Button>
          </div>
        </div>
        <LiveAlertsRail eventsTotal={stats.events} objectsTotal={stats.objects} cameras={cameras.length} />
        {expandedCamera ? (
          <ExpandedCameraView camera={expandedCamera} onClose={() => setExpandedKey(null)} />
        ) : (
          <div className={mode === 'fit' ? 'live-grid-shell' : undefined}>
            <CameraGrid
              cameras={ordered}
              cols={effectiveCols}
              mode={mode}
              onOpenStream={(rid, sid) => setStream({ rid, sid })}
              onReorder={setOrder}
              onExpand={setExpandedKey}
              getPreviewBlob={(sid) => previewWs.getBlobUrl(sid)}
              previewWsActive={previewWs.connected}
              loading={camerasLoading}
            />
          </div>
        )}
      </div>
      {stream ? <StreamOverlay rid={stream.rid} sourceId={stream.sid} onClose={() => setStream(null)} /> : null}
    </section>
  );
}
