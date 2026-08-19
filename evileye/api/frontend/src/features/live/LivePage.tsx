import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { stateApi, journalsApi, streamStatus, type StateCamera, cacheGet, cacheSet, isAbortError } from '../../api';
import { ApiError } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { Button } from '../../components/ui';
import { StreamOverlay } from '../../components/StreamOverlay';
import { useVisibilityPolling } from '../../hooks/useVisibilityPolling';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';
import { CameraGrid } from './CameraGrid';
import { ExpandedCameraView } from './ExpandedCameraView';
import { LiveAlertsRail } from './LiveAlertsRail';
import { useLiveLayout } from './useLiveLayout';
import { useLiveGridPreviewWs } from './useLiveGridPreviewWs';
import { fitColsForCount } from '../layout/fitGrid';

const CAMERAS_CACHE_KEY = 'state:cameras:current';
const STATS_CACHE_KEY = 'journals:stats';
const CAMERAS_TTL_MS = 8_000;
const STATS_TTL_MS = 20_000;

export function LivePage() {
  const { showError } = useToast();
  const { t } = useI18n();
  const { refresh } = useAuth();
  const cachedCams = cacheGet<{ items: StateCamera[] }>(CAMERAS_CACHE_KEY);
  const cachedStats = cacheGet<{ available: boolean; events_total?: number; objects_total?: number }>(STATS_CACHE_KEY);
  const [cameras, setCameras] = useState<StateCamera[]>(() => cachedCams?.items ?? []);
  const [camerasLoading, setCamerasLoading] = useState(() => !(cachedCams?.items?.length));
  const camerasRef = useRef(cameras);
  camerasRef.current = cameras;
  const [stats, setStats] = useState<{ events?: number; objects?: number }>(() =>
    cachedStats?.available
      ? { events: cachedStats.events_total, objects: cachedStats.objects_total }
      : {},
  );
  const [stream, setStream] = useState<{ rid: number; sid: number | null } | null>(null);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const { cols, setCols, order, setOrder, mode, setMode } = useLiveLayout();
  const abortRef = useRef<AbortController | null>(null);
  const camerasLoadingTimerRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    // Avoid "Searching…" flicker on transient backend hiccups.
    if (camerasLoadingTimerRef.current != null) {
      window.clearTimeout(camerasLoadingTimerRef.current);
      camerasLoadingTimerRef.current = null;
    }
    if (!camerasRef.current.length && !cacheGet(CAMERAS_CACHE_KEY)) {
      camerasLoadingTimerRef.current = window.setTimeout(() => setCamerasLoading(true), 1500);
    } else {
      setCamerasLoading(false);
    }
    try {
      const [camCurrent, st] = await Promise.all([
        stateApi.cameras('current', { signal: ac.signal }),
        journalsApi.stats(undefined, { signal: ac.signal }).catch(() => null),
      ]);
      if (ac.signal.aborted) return;
      let camRes = camCurrent;
      if (!(camCurrent.items ?? []).length) {
        camRes = await stateApi.cameras('active', { signal: ac.signal });
        if (ac.signal.aborted) return;
      }
      cacheSet(CAMERAS_CACHE_KEY, camRes, CAMERAS_TTL_MS);
      setCameras(camRes.items ?? []);
      if (st?.available) {
        cacheSet(STATS_CACHE_KEY, st, STATS_TTL_MS);
        setStats({ events: st.events_total, objects: st.objects_total });
      }
    } catch (e) {
      if (isAbortError(e) || ac.signal.aborted) return;
      if (e instanceof ApiError && e.status === 401) {
        void refresh();
        return;
      }
      showError(e instanceof Error ? e.message : t('live.empty'));
    } finally {
      if (camerasLoadingTimerRef.current != null) {
        window.clearTimeout(camerasLoadingTimerRef.current);
        camerasLoadingTimerRef.current = null;
      }
      if (!ac.signal.aborted) setCamerasLoading(false);
    }
  }, [showError, refresh, t]);

  useEffect(() => () => abortRef.current?.abort(), []);

  useVisibilityPolling(load, 10_000, true, 0);

  const primaryRunId = useMemo(() => {
    const ids = [...new Set(cameras.map((c) => c.run_id).filter((id) => Number.isFinite(id)))];
    return ids.length === 1 ? ids[0] : ids[0] ?? null;
  }, [cameras]);

  const previewSourceIds = useMemo(
    () =>
      Array.from(new Set(cameras.map((c) => c.source_id).filter((id): id is number => id != null))).sort(
        (a, b) => a - b,
      ),
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
      <div className={`card${mode === 'fit' ? ' live-page-card expanded-camera-view-host' : ' expanded-camera-view-host'}`}>
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
