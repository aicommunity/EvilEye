import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  playbackApi,
  stateApi,
  type PlaybackCamera,
  type PlaybackEventMarker,
  type PlaybackSegment,
  cacheGet,
  cacheSet,
  isAbortError,
} from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';
import { useRunConfigFlags } from '../../hooks/useRunConfigFlags';
import { Timeline } from './Timeline';
import { PlaybackGrid } from './PlaybackGrid';
import { ExpandedPlaybackView } from './ExpandedPlaybackView';
import { usePlaybackController } from './usePlaybackController';
import { useDetectionIndex } from './useDetectionIndex';
import { usePlaybackLayout } from './usePlaybackLayout';
import { useTimelineViewport } from './useTimelineViewport';
import { fitColsForCount } from '../layout/fitGrid';
import { formatPlaybackDateTime, localDateString, mergeSegments, dayBoundsLocal, dayViewUpperBound, clampViewToDayBounds, segmentIntersectsDay } from './timelineMath';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

const INITIAL_WINDOW_SEC = 7200;
const SEGMENTS_LOAD_TIMEOUT_MS = 15_000;
/** Half-width of the time range requested when seeking outside loaded data. */
const SEEK_LOAD_HALF_SEC = 3600;

function initialSegmentWindow(dateStr: string): { from: number; to: number } {
  const { start, end } = dayBoundsLocal(dateStr);
  const nowSec = Date.now() / 1000;
  if (dateStr === today()) {
    const to = Math.min(end, nowSec);
    const from = Math.max(start, nowSec - INITIAL_WINDOW_SEC);
    return { from, to };
  }
  return { from: Math.max(start, end - INITIAL_WINDOW_SEC), to: end };
}

function parseDeepLinkTime(raw: string | null): number | null {
  if (!raw) return null;
  const n = Number(raw);
  if (Number.isFinite(n) && n > 0) return n;
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed / 1000 : null;
}

const CAMERAS_TTL_MS = 30_000;
const SEGMENTS_TTL_MS = 15_000;

function camerasCacheKey(date: string, runId: number | null): string {
  return `playback:cameras:${date}:${runId ?? 'none'}`;
}

export function PlaybackPage() {
  const [params] = useSearchParams();
  const { showError } = useToast();
  const { t } = useI18n();
  const flags = useRunConfigFlags();
  const [date, setDate] = useState(today());
  const [runId, setRunId] = useState<number | null>(null);
  const [runReady, setRunReady] = useState(false);
  const [cameras, setCameras] = useState<PlaybackCamera[]>([]);
  const [camerasLoading, setCamerasLoading] = useState(false);
  const { cols, setCols, selectedIds, setSelectedIds, mode, setMode } = usePlaybackLayout();
  const [segmentsByCam, setSegmentsByCam] = useState<Record<string, PlaybackSegment[]>>({});
  const [markers, setMarkers] = useState<PlaybackEventMarker[]>([]);
  const [segmentsLoaded, setSegmentsLoaded] = useState(false);
  const [segmentsLoading, setSegmentsLoading] = useState(false);
  const [showMetadata, setShowMetadata] = useState(true);
  const [scrubbing, setScrubbing] = useState(false);
  const [expandedCameraId, setExpandedCameraId] = useState<string | null>(null);
  const initialT = parseDeepLinkTime(params.get('t'));
  const ctrl = usePlaybackController(initialT);
  const viewport = useTimelineViewport();
  const detectionWindow = useMemo(() => {
    const { start } = dayBoundsLocal(date);
    return { fromSec: start, toSec: dayViewUpperBound(date) };
  }, [date]);
  const detectionIndex = useDetectionIndex({
    cameras: selectedIds,
    date,
    runId,
    fromSec: detectionWindow.fromSec,
    toSec: detectionWindow.toSec,
    enabled: showMetadata && selectedIds.length > 0,
  });
  useEffect(() => {
    ctrl.setDetectionTimestamps(detectionIndex.globalTs);
    ctrl.setSkipEnabled(showMetadata);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- controller setters are stable
  }, [detectionIndex.globalTs, showMetadata]);

  useEffect(() => {
    ctrl.setScrubbing(scrubbing);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- controller setters are stable
  }, [scrubbing]);

  const togglePlay = useCallback(() => {
    ctrl.setPlaying(!ctrl.playing);
  }, [ctrl]);

  const urlCamera = params.get('camera');
  const dateChangeSourceRef = useRef<'user' | 'viewport'>('user');
  const skipHardSegmentReloadRef = useRef(false);
  const loadTimerRef = useRef<number | null>(null);
  const selectedIdsRef = useRef(selectedIds);
  selectedIdsRef.current = selectedIds;
  const camerasAbortRef = useRef<AbortController | null>(null);
  const segmentsAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    void stateApi
      .runs('current', { signal: ac.signal })
      .then((res) => {
        if (ac.signal.aborted) return;
        const items = Array.isArray(res) ? res : res.items ?? [];
        const running = items.find((r) => r.state === 'running') ?? items[0];
        if (running?.id) setRunId(running.id);
      })
      .catch((e) => {
        if (isAbortError(e)) return;
      })
      .finally(() => {
        if (!ac.signal.aborted) setRunReady(true);
      });
    return () => ac.abort();
  }, []);

  const softRefreshCameras = useCallback(
    async (nextDate: string) => {
      try {
        const camRes = await playbackApi.cameras(nextDate, runId);
        cacheSet(camerasCacheKey(nextDate, runId), camRes, CAMERAS_TTL_MS);
        setCameras(camRes.items);
        const ids = new Set(camRes.items.map((c) => c.id));
        setSelectedIds((prev) => {
          const kept = prev.filter((id) => ids.has(id));
          return kept.length ? kept : prev;
        });
      } catch {
        /* keep current cameras on soft refresh failure */
      }
    },
    [runId, setSelectedIds],
  );

  useEffect(() => {
    if (!runReady) return;
    let cancelled = false;
    if (dateChangeSourceRef.current === 'viewport') {
      dateChangeSourceRef.current = 'user';
      skipHardSegmentReloadRef.current = true;
      void softRefreshCameras(date);
      return;
    }
    camerasAbortRef.current?.abort();
    const ac = new AbortController();
    camerasAbortRef.current = ac;
    void (async () => {
      const cacheKey = camerasCacheKey(date, runId);
      const cached = cacheGet<{ items: PlaybackCamera[] }>(cacheKey);
      if (cached?.items?.length) {
        setCameras(cached.items);
        setCamerasLoading(false);
      } else {
        setCamerasLoading(true);
      }
      try {
        const camRes = await playbackApi.cameras(date, runId, { signal: ac.signal });
        if (cancelled || ac.signal.aborted) return;
        cacheSet(cacheKey, camRes, CAMERAS_TTL_MS);
        setCameras(camRes.items);
        const ids = new Set(camRes.items.map((c) => c.id));
        setSelectedIds((prev) => {
          const kept = prev.filter((id) => ids.has(id));
          if (kept.length) return kept;
          if (urlCamera && ids.has(urlCamera)) return [urlCamera];
          return camRes.items.map((c) => c.id);
        });
        setSegmentsByCam({});
        setMarkers([]);
        setSegmentsLoaded(false);
      } catch (e) {
        if (isAbortError(e) || cancelled) return;
        showError(e instanceof Error ? e.message : t('playback.unavailable'));
      } finally {
        if (!cancelled && !ac.signal.aborted) setCamerasLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      ac.abort();
    };
  }, [date, runId, runReady, showError, urlCamera, setSelectedIds, softRefreshCameras]);

  const loadSegments = useCallback(
    async (camsOverride?: string[], opts?: { from?: number; to?: number; merge?: boolean; date?: string }) => {
      segmentsAbortRef.current?.abort();
      const ac = new AbortController();
      segmentsAbortRef.current = ac;
      const timeoutId = window.setTimeout(() => ac.abort(), SEGMENTS_LOAD_TIMEOUT_MS);
      const isInitialLoad = !opts?.merge;
      if (isInitialLoad) setSegmentsLoading(true);
      try {
        const nextSelected = camsOverride ?? selectedIdsRef.current;
        if (!nextSelected.length) {
          setSegmentsByCam({});
          setMarkers([]);
          setSegmentsLoaded(true);
          if (!opts?.merge) {
            viewport.resetToData(null, null, opts?.date ?? date);
          }
          return;
        }
        const useDate = opts?.date ?? date;
        const segKey = `playback:segments:${useDate ?? ''}:${opts?.from ?? ''}:${opts?.to ?? ''}:${nextSelected.join(',')}`;
        const evKey = `playback:events:${useDate ?? ''}:${opts?.from ?? ''}:${opts?.to ?? ''}:${nextSelected.join(',')}`;

        const [batch, ev] = await Promise.all([
          playbackApi.segmentsBatch(nextSelected, opts?.from, opts?.to, useDate, {
            signal: ac.signal,
            runId,
          }),
          playbackApi.events(opts?.from, opts?.to, undefined, useDate, nextSelected, {
            signal: ac.signal,
          }),
        ]);
        if (ac.signal.aborted) return;

        if (!opts?.merge) {
          cacheSet(segKey, batch, SEGMENTS_TTL_MS);
          cacheSet(evKey, ev, SEGMENTS_TTL_MS);
        }

        const incoming: Record<string, PlaybackSegment[]> = { ...(batch.by_camera || {}) };
        for (const id of nextSelected) {
          if (!incoming[id]) incoming[id] = [];
        }
        setSegmentsByCam((prev) => {
          if (!opts?.merge) return incoming;
          const merged: Record<string, PlaybackSegment[]> = { ...prev };
          for (const id of nextSelected) {
            merged[id] = mergeSegments(prev[id] ?? [], incoming[id] ?? []);
          }
          return merged;
        });
        const allSegs = Object.values(incoming).flat();
        const from = allSegs.length ? Math.min(...allSegs.map((s) => s.start_ts)) : opts?.from;
        const to = allSegs.length ? Math.max(...allSegs.map((s) => s.end_ts)) : opts?.to;
        if (from != null && to != null) {
          viewport.expandLoaded(from, to);
          ctrl.setRange(
            opts?.merge ? Math.min(ctrl.fromSec ?? from, from) : from,
            opts?.merge ? Math.max(ctrl.toSec ?? to, to) : to,
            { preservePosition: Boolean(opts?.merge) || initialT != null },
          );
        }
        if (!opts?.merge) {
          viewport.resetToData(from ?? null, to ?? null, useDate ?? date);
        }
        setMarkers((prev) => {
          if (!opts?.merge) return ev.items;
          const byKey = new Map<string, PlaybackEventMarker>();
          for (const m of prev) byKey.set(`${m.ts}:${m.camera}:${m.type}`, m);
          for (const m of ev.items) byKey.set(`${m.ts}:${m.camera}:${m.type}`, m);
          return Array.from(byKey.values()).sort((a, b) => a.ts - b.ts);
        });
        setSegmentsLoaded(true);
        if (!opts?.merge && initialT != null) ctrl.seek(initialT);
      } catch (e) {
        if (isAbortError(e)) {
          if (isInitialLoad) {
            setSegmentsLoaded(true);
            showError(t('playback.unavailable'));
          }
          return;
        }
        showError(e instanceof Error ? e.message : t('playback.unavailable'));
      } finally {
        window.clearTimeout(timeoutId);
        if (isInitialLoad) setSegmentsLoading(false);
      }
    },
    [date, initialT, showError, ctrl, viewport, runId, t],
  );
  useEffect(() => {
    // Show calendar-day timeline immediately on date change (before segments return).
    viewport.resetToData(null, null, date);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on date
  }, [date]);

  useEffect(() => {
    if (!selectedIds.length || camerasLoading) return;
    if (skipHardSegmentReloadRef.current) {
      skipHardSegmentReloadRef.current = false;
      return;
    }
    void loadSegments(selectedIds, initialSegmentWindow(date));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on date/selection only
  }, [date, selectedIds, camerasLoading]);

  const ensureAdjacentLoad = useCallback(
    (vf: number, vt: number) => {
      const { needFrom, needTo, needed } = viewport.needsLoad(vf, vt, date);
      if (!needed) return;
      if (loadTimerRef.current) window.clearTimeout(loadTimerRef.current);
      loadTimerRef.current = window.setTimeout(() => {
        void loadSegments(selectedIdsRef.current, {
          from: needFrom,
          to: needTo,
          merge: true,
          date,
        });
      }, 250);
    },
    [loadSegments, viewport, date],
  );

  const onViewChange = useCallback(
    (vf: number, vt: number) => {
      const clamped = clampViewToDayBounds(vf, vt, date);
      viewport.setView(clamped.viewFrom, clamped.viewTo);
      ensureAdjacentLoad(clamped.viewFrom, clamped.viewTo);
    },
    [viewport, ensureAdjacentLoad, date],
  );

  const seek = useCallback(
    (sec: number) => {
      ctrl.seek(sec);
      ensureAdjacentLoad(sec - SEEK_LOAD_HALF_SEC, sec + SEEK_LOAD_HALF_SEC);
    },
    [ctrl, ensureAdjacentLoad],
  );

  const toggleCamera = (id: string) => {
    const on = selectedIds.includes(id);
    const next = on ? selectedIds.filter((x) => x !== id) : [...selectedIds, id];
    setSelectedIds(next);
  };

  const cameraDefs = useMemo(() => Object.fromEntries(cameras.map((c) => [c.id, c])), [cameras]);
  const expandedCamera = useMemo(() => {
    if (!expandedCameraId) return null;
    if (!selectedIds.includes(expandedCameraId)) return null;
    const cam = cameraDefs[expandedCameraId];
    if (!cam) return null;
    return cam;
  }, [expandedCameraId, selectedIds, cameraDefs]);

  useEffect(() => {
    if (!expandedCameraId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExpandedCameraId(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [expandedCameraId]);

  useEffect(() => {
    if (!expandedCameraId) return;
    if (!selectedIds.includes(expandedCameraId)) {
      setExpandedCameraId(null);
      return;
    }
    if (segmentsLoaded && !(segmentsByCam[expandedCameraId]?.length)) {
      setExpandedCameraId(null);
    }
  }, [expandedCameraId, selectedIds, segmentsLoaded, segmentsByCam]);

  useEffect(() => {
    setExpandedCameraId(null);
  }, [date]);

  const allSegments = useMemo(
    () => Object.values(segmentsByCam).flat().filter((s) => segmentIntersectsDay(s, date)),
    [segmentsByCam, date],
  );
  const timelineMarkers = useMemo(() => {
    const { start, end } = dayBoundsLocal(date);
    return markers.filter((m) => m.ts >= start && m.ts < end);
  }, [markers, date]);
  const effectiveCols = mode === 'fit' ? fitColsForCount(selectedIds.length) : cols;
  const positionLabel = formatPlaybackDateTime(ctrl.positionSec);
  const detectionsReady = !detectionIndex.loading;

  let gridEmpty: string | null = null;
  if (camerasLoading) gridEmpty = t('playback.loadingCamerasGrid');
  else if (!cameras.length) gridEmpty = t('playback.noCamerasForDate');
  else if (!selectedIds.length) gridEmpty = t('playback.selectCameras');

  return (
    <section className={`panel active playback-page${mode === 'fit' ? ' playback-page--fit' : ''}`}>
      <div className="card playback-card">
        <div className="toolbar" style={{ justifyContent: 'space-between', flexWrap: 'wrap' }}>
          <div>
            <h2 style={{ margin: 0 }}>{t('playback.title')}</h2>
            <p className="hint">{t('playback.hint')}</p>
          </div>
          <div className="toolbar">
            <input
              type="date"
              className="search-input"
              value={date}
              onChange={(e) => {
                dateChangeSourceRef.current = 'user';
                setDate(e.target.value);
              }}
            />
            <span className="hint playback-position-clock" title={t('playback.currentTime')}>
              {positionLabel}
            </span>
            <Button size="sm" variant={mode === 'fit' ? 'primary' : 'outline'} onClick={() => setMode('fit')}>
              {t('layout.fit')}
            </Button>
            <Button size="sm" variant={mode === 'fixed' ? 'primary' : 'outline'} onClick={() => setMode('fixed')}>
              {t('layout.fixed')}
            </Button>
            {mode === 'fixed'
              ? [1, 2, 3, 4].map((n) => (
                  <Button key={n} size="sm" variant={cols === n ? 'primary' : 'outline'} onClick={() => setCols(n)}>
                    {n}
                  </Button>
                ))
              : null}
            <Button size="sm" variant={ctrl.playing ? 'danger' : 'success'} onClick={togglePlay}>
              {ctrl.playing ? t('playback.pause') : t('playback.play')}
            </Button>
            {[0.5, 1, 2, 4].map((s) => (
              <Button key={s} size="sm" variant={ctrl.speed === s ? 'primary' : 'outline'} onClick={() => ctrl.setSpeed(s)}>
                {s}x
              </Button>
            ))}
            <label className="hint" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <input
                type="checkbox"
                checked={showMetadata}
                onChange={(e) => setShowMetadata(e.target.checked)}
              />
              {t('playback.showMetadata')}
            </label>
          </div>
        </div>
        {!flags.loading && flags.recordingEnabled === false ? (
          <p className="setup-banner">{t('playback.recordingDisabled')}</p>
        ) : null}
        <div className="toolbar" style={{ flexWrap: 'wrap' }}>
          {camerasLoading ? <span className="hint">{t('playback.loadingCameras')}</span> : null}
          {!camerasLoading && !cameras.length ? <span className="hint">{t('playback.noCameras')}</span> : null}
          {cameras.map((c) => {
            const on = selectedIds.includes(c.id);
            return (
              <Button key={c.id} size="sm" variant={on ? 'primary' : 'outline'} onClick={() => toggleCamera(c.id)}>
                {c.name}
              </Button>
            );
          })}
        </div>
        <div className="playback-main expanded-camera-view-host">
          {expandedCamera ? (
            <ExpandedPlaybackView
              cameraId={expandedCamera.id}
              camera={expandedCamera}
              segments={segmentsByCam[expandedCamera.id] ?? []}
              getPosition={ctrl.getPosition}
              positionSec={ctrl.positionSec}
              playing={ctrl.playing}
              speed={ctrl.speed}
              runId={runId}
              showMetadata={showMetadata}
              playMode="normal"
              scrubbing={scrubbing}
              detectionItems={detectionIndex.byCamera[expandedCamera.id] ?? []}
              globalDetectionTs={detectionIndex.globalTs}
              onVideoClock={ctrl.syncPositionFromVideo}
              onClose={() => setExpandedCameraId(null)}
              detectionsReady={detectionsReady}
            />
          ) : gridEmpty ? (
            <p className="empty">{gridEmpty}</p>
          ) : (
            <PlaybackGrid
              cameras={selectedIds}
              cameraDefs={cameraDefs}
              cols={effectiveCols}
              mode={mode}
              segmentsByCam={segmentsByCam}
              getPosition={ctrl.getPosition}
              positionSec={ctrl.positionSec}
              playing={ctrl.playing}
              speed={ctrl.speed}
              runId={runId}
              showMetadata={showMetadata}
              playMode="normal"
              scrubbing={scrubbing}
              detectionByCamera={detectionIndex.byCamera}
              globalDetectionTs={detectionIndex.globalTs}
              onVideoClock={ctrl.syncPositionFromVideo}
              onExpand={setExpandedCameraId}
              segmentsLoading={segmentsLoading}
              detectionsReady={detectionsReady}
            />
          )}
        </div>
        <div className="playback-timeline-footer">
          <p className="hint" style={{ margin: '0 0 2px', fontSize: '0.75rem' }}>
            {t('playback.timelineHint')}
          </p>
          <Timeline
            viewFrom={viewport.viewFrom}
            viewTo={viewport.viewTo}
            position={ctrl.positionSec}
            markers={timelineMarkers}
            segments={allSegments}
            detectionTs={detectionIndex.globalTs}
            onSeek={seek}
            onViewChange={onViewChange}
            onScrubbingChange={setScrubbing}
          />
        </div>
      </div>
    </section>
  );
}
