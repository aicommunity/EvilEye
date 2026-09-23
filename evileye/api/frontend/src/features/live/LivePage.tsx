import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { stateApi, journalsApi, streamStatus, type StateCamera, cacheGet, cacheSet, cacheInvalidate, formatApiError, isAbortError, ApiError } from '../../api';
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
import { LIVE_CAMERAS_CACHE_KEY, mergeLiveCameraPoll, resetLiveCameraCache } from './mergeLiveCameraPoll';
import { cancelPreviewDemandGrace, startPreviewDemandGrace } from './previewDemandGrace';
import { fitColsForCount } from '../layout/fitGrid';

const CAMERAS_CACHE_KEY = LIVE_CAMERAS_CACHE_KEY;
const STATS_CACHE_KEY = 'journals:stats';
const CAMERAS_TTL_MS = 12_000;
const STATS_TTL_MS = 20_000;
const PREVIEW_DEMAND_MS = 5_000;
const HEALTH_TICK_MS = 1_000;
const EMPTY_CAMERA_GRACE_POLLS = 2;

/** Last non-empty Live camera list in this tab (survives section remount). */
let lastGoodLiveCameras: StateCamera[] = [];
let emptyCameraPollStreak = 0;
let lastLiveUsername: string | null = null;

export function LivePage() {
  const { showError } = useToast();
  const { t } = useI18n();
  const { refresh, user } = useAuth();
  const username = user?.username ?? null;

  const cachedCams = cacheGet<{ items: StateCamera[] }>(CAMERAS_CACHE_KEY);
  const cachedStats = cacheGet<{ available: boolean; events_total?: number; objects_total?: number }>(STATS_CACHE_KEY);
  const [cameras, setCameras] = useState<StateCamera[]>(
    () => (cachedCams?.items?.length ? cachedCams.items : lastGoodLiveCameras),
  );
  const [camerasLoading, setCamerasLoading] = useState(() => !(cachedCams?.items?.length));
  const [camerasPolledAtMs, setCamerasPolledAtMs] = useState(() => Date.now());
  const [healthTick, setHealthTick] = useState(0);
  const camerasRef = useRef(cameras);
  camerasRef.current = cameras;
  const [stats, setStats] = useState<{ events?: number; objects?: number }>(() =>
    cachedStats?.available
      ? { events: cachedStats.events_total, objects: cachedStats.objects_total }
      : {},
  );

  useEffect(() => {
    if (username !== lastLiveUsername) {
      lastLiveUsername = username;
      const reset = resetLiveCameraCache(cacheInvalidate);
      lastGoodLiveCameras = reset.lastGood;
      emptyCameraPollStreak = reset.emptyStreak;
      setCameras([]);
    }
  }, [username]);
  const [stream, setStream] = useState<{ rid: number; sid: number | null } | null>(null);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const { cols, setCols, order, setOrder, mode, setMode } = useLiveLayout();
  const abortRef = useRef<AbortController | null>(null);
  const camerasLoadingTimerRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
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
      const camCurrent = await stateApi.cameras('current', { signal: ac.signal });
      if (ac.signal.aborted) return;
      let camRes = camCurrent;
      if (!(camCurrent.items ?? []).length) {
        camRes = await stateApi.cameras('active', { signal: ac.signal });
        if (ac.signal.aborted) return;
      }
      const items = camRes.items ?? [];
      const decision = mergeLiveCameraPoll(
        items,
        camerasRef.current,
        lastGoodLiveCameras,
        emptyCameraPollStreak,
        EMPTY_CAMERA_GRACE_POLLS,
      );
      emptyCameraPollStreak = decision.emptyStreak;
      lastGoodLiveCameras = decision.lastGood;
      if (decision.cleared || items.length) {
        cacheSet(CAMERAS_CACHE_KEY, { items: decision.cameras }, CAMERAS_TTL_MS);
      }
      setCameras(decision.cameras);
      setCamerasPolledAtMs(Date.now());
      void journalsApi
        .stats(undefined, { signal: ac.signal })
        .then((st) => {
          if (ac.signal.aborted || !st?.available) return;
          cacheSet(STATS_CACHE_KEY, st, STATS_TTL_MS);
          setStats({ events: st.events_total, objects: st.objects_total });
        })
        .catch(() => undefined);
    } catch (e) {
      if (isAbortError(e) || ac.signal.aborted) return;
      if (e instanceof ApiError && e.status === 401) {
        void refresh();
        return;
      }
      showError(formatApiError(e, t));
    } finally {
      if (camerasLoadingTimerRef.current != null) {
        window.clearTimeout(camerasLoadingTimerRef.current);
        camerasLoadingTimerRef.current = null;
      }
      if (!ac.signal.aborted) setCamerasLoading(false);
    }
  }, [showError, refresh, t]);

  useEffect(() => () => abortRef.current?.abort(), []);

  useVisibilityPolling(load, 15_000, true, 0);

  useEffect(() => {
    const id = window.setInterval(() => setHealthTick((n) => n + 1), HEALTH_TICK_MS);
    return () => window.clearInterval(id);
  }, []);

  const [activeSources, setActiveSources] = useState<Array<{ runId: number; sourceId: number | null }>>([]);
  const activeSourcesRef = useRef(activeSources);
  activeSourcesRef.current = activeSources;

  // B01: subscribe only visible/active tiles (fallback to all until IO reports).
  const previewByRun = useMemo(() => {
    const m = new Map<number, number[]>();
    const source =
      activeSources.length > 0
        ? activeSources
        : cameras.map((c) => ({ runId: c.run_id, sourceId: c.source_id ?? null }));
    for (const { runId, sourceId } of source) {
      if (!Number.isFinite(runId) || sourceId == null) continue;
      const list = m.get(runId) ?? [];
      if (!list.includes(sourceId)) list.push(sourceId);
      m.set(runId, list);
    }
    return m;
  }, [cameras, activeSources]);

  const previewWs = useLiveGridPreviewWs(previewByRun);

  useEffect(() => {
    cancelPreviewDemandGrace();
    if (!cameras.length) return;

    const tick = () => {
      const active = activeSourcesRef.current;
      if (active.length) {
        const seen = new Set<string>();
        for (const { runId, sourceId } of active) {
          const key = `${runId}:${sourceId ?? 'all'}`;
          if (seen.has(key)) continue;
          seen.add(key);
          void streamStatus(runId, sourceId).catch(() => undefined);
        }
        return;
      }
      const runIds = new Set<number>();
      for (const cam of cameras) {
        if (Number.isFinite(cam.run_id)) runIds.add(cam.run_id);
      }
      for (const rid of runIds) {
        void streamStatus(rid, null).catch(() => undefined);
      }
    };
    tick();
    const id = window.setInterval(tick, PREVIEW_DEMAND_MS);
    return () => {
      window.clearInterval(id);
      const runIds = new Set<number>();
      for (const cam of cameras) {
        if (Number.isFinite(cam.run_id)) runIds.add(cam.run_id);
      }
      startPreviewDemandGrace(runIds);
    };
  }, [cameras]);

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
            <Button size="sm" variant="outline" onClick={() => void load()}>
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
              getPreviewBlob={(rid, sid) => previewWs.getBlobUrl(rid, sid)}
              getPreviewFrameAgeSec={(rid, sid) => previewWs.getPreviewFrameAgeSec(rid, sid)}
              previewWsActive={previewWs.connected}
              camerasPolledAtMs={camerasPolledAtMs}
              healthTick={healthTick}
              onActiveSourcesChange={setActiveSources}
              loading={camerasLoading}
            />
          </div>
        )}
      </div>
      {stream ? <StreamOverlay rid={stream.rid} sourceId={stream.sid} onClose={() => setStream(null)} /> : null}
    </section>
  );
}
