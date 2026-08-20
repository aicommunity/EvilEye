import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  playbackApi,
  stateApi,
  type PlaybackCamera,
  type PlaybackEventInterval,
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
import { formatPlaybackDateTime, localDateString, mergeSegments, dayBoundsLocal, dayViewUpperBound, clampViewToDayBounds, segmentIntersectsDay, snapPositionToPlayable } from './timelineMath';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

const INITIAL_WINDOW_SEC = 7200;
const SEGMENTS_LOAD_TIMEOUT_MS = 15_000;
/** Half-width of the time range requested when seeking outside loaded data. */
const SEEK_LOAD_HALF_SEC = 3600;

function initialSegmentWindow(dateStr: string, anchorSec?: number | null): { from: number; to: number } {
  const { start, end } = dayBoundsLocal(dateStr);
  if (anchorSec != null && Number.isFinite(anchorSec) && anchorSec >= start && anchorSec <= end) {
    return {
      from: Math.max(start, anchorSec - SEEK_LOAD_HALF_SEC),
      to: Math.min(end, anchorSec + SEEK_LOAD_HALF_SEC),
    };
  }
  const nowSec = Date.now() / 1000;
  if (dateStr === today()) {
    const to = Math.min(end, nowSec);
    const from = Math.max(start, nowSec - INITIAL_WINDOW_SEC);
    return { from, to };
  }
  return { from: Math.max(start, end - INITIAL_WINDOW_SEC), to: end };
}

function dateFromUnixSec(sec: number): string {
  const d = new Date(sec * 1000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
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
/** Padding around viewport/position for the priority detection fetch. */
const DETECTION_PRIORITY_PAD_SEC = 900;
const VIEWPORT_DEBOUNCE_MS = 350;
const SEEK_SETTLE_HOLD_MS = 800;

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

function camerasCacheKey(date: string, runId: number | null): string {
  return `playback:cameras:${date}:${runId ?? 'none'}`;
}

export function PlaybackPage() {
  const [params] = useSearchParams();
  const { showError } = useToast();
  const { t } = useI18n();
  const flags = useRunConfigFlags();
  const initialT = parseDeepLinkTime(params.get('t'));
  const [date, setDate] = useState(() => (initialT != null ? dateFromUnixSec(initialT) : today()));
  const [runId, setRunId] = useState<number | null>(null);
  const [runResolved, setRunResolved] = useState(false);
  const [cameras, setCameras] = useState<PlaybackCamera[]>([]);
  const [camerasLoading, setCamerasLoading] = useState(false);
  const { cols, setCols, selectedIds, setSelectedIds, mode, setMode } = usePlaybackLayout();
  const [segmentsByCam, setSegmentsByCam] = useState<Record<string, PlaybackSegment[]>>({});
  const [markers, setMarkers] = useState<PlaybackEventMarker[]>([]);
  const [eventIntervals, setEventIntervals] = useState<PlaybackEventInterval[]>([]);
  const [segmentsLoaded, setSegmentsLoaded] = useState(false);
  const [segmentsLoading, setSegmentsLoading] = useState(false);
  const [showMetadata, setShowMetadata] = useState(true);
  const [, setTimelinePanning] = useState(false);
  const [seekSettling, setSeekSettling] = useState(false);
  const [expandedCameraId, setExpandedCameraId] = useState<string | null>(null);
  const ctrl = usePlaybackController(initialT);
  const viewport = useTimelineViewport();

  useEffect(() => {
    const linked = parseDeepLinkTime(params.get('t'));
    if (linked == null) return;
    setDate(dateFromUnixSec(linked));
    ctrl.seek(linked);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sync deep link when query changes
  }, [params]);
  const debouncedViewFrom = useDebouncedValue(viewport.viewFrom, VIEWPORT_DEBOUNCE_MS);
  const debouncedViewTo = useDebouncedValue(viewport.viewTo, VIEWPORT_DEBOUNCE_MS);
  const seekSettleTimerRef = useRef<number | null>(null);
  const dayBounds = useMemo(() => {
    const { start } = dayBoundsLocal(date);
    return { fromSec: start, toSec: dayViewUpperBound(date) };
  }, [date]);

  const priorityDetectionWindow = useMemo(() => {
    const { start } = dayBoundsLocal(date);
    const upper = dayViewUpperBound(date);
    // Keep priority fetch local to playhead/viewport — do not expand to ctrl.fromSec/toSec
    // (loaded segment bounds span the whole day and would force a full-day rebuild).
    const anchors: number[] = [
      ctrl.positionSec - SEEK_LOAD_HALF_SEC,
      ctrl.positionSec + SEEK_LOAD_HALF_SEC,
    ];
    if (debouncedViewFrom != null) anchors.push(debouncedViewFrom - DETECTION_PRIORITY_PAD_SEC);
    if (debouncedViewTo != null) anchors.push(debouncedViewTo + DETECTION_PRIORITY_PAD_SEC);
    const finite = anchors.filter((v) => Number.isFinite(v));
    if (!finite.length) return null;
    return {
      fromSec: Math.max(start, Math.min(...finite)),
      toSec: Math.min(upper, Math.max(...finite)),
    };
  }, [date, ctrl.positionSec, debouncedViewFrom, debouncedViewTo]);

  const detectionIndex = useDetectionIndex({
    cameras: selectedIds,
    date,
    runId,
    priorityFromSec: priorityDetectionWindow?.fromSec ?? null,
    priorityToSec: priorityDetectionWindow?.toSec ?? null,
    backgroundFromSec: dayBounds.fromSec,
    backgroundToSec: dayBounds.toSec,
    enabled: showMetadata && selectedIds.length > 0,
  });
  useEffect(() => {
    ctrl.setDetectionTimestamps(detectionIndex.globalTs);
    ctrl.setSkipEnabled(showMetadata);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- controller setters are stable
  }, [detectionIndex.globalTs, showMetadata]);

  useEffect(() => {
    ctrl.setScrubbing(seekSettling);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- controller setters are stable
  }, [seekSettling]);

  const togglePlay = useCallback(() => {
    if (ctrl.playing && seekSettleTimerRef.current != null) {
      window.clearTimeout(seekSettleTimerRef.current);
      seekSettleTimerRef.current = null;
      setSeekSettling(false);
    }
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
      .runs('active', { signal: ac.signal })
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
        if (!ac.signal.aborted) setRunResolved(true);
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
    if (!runResolved) return;
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
        let camRes = await playbackApi.cameras(date, runId, { signal: ac.signal });
        if (cancelled || ac.signal.aborted) return;
        if (!camRes.items.length && runId != null) {
          camRes = await playbackApi.cameras(date, null, { signal: ac.signal });
        }
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
  }, [date, runId, runResolved, showError, urlCamera, setSelectedIds, softRefreshCameras]);

  const loadSegments = useCallback(
    async (camsOverride?: string[], opts?: { from?: number; to?: number; merge?: boolean; date?: string }) => {
      segmentsAbortRef.current?.abort();
      const ac = new AbortController();
      segmentsAbortRef.current = ac;
      const timeoutId = window.setTimeout(() => ac.abort(), SEGMENTS_LOAD_TIMEOUT_MS);
      const isInitialLoad = !opts?.merge;
      let didSetSegmentsLoading = false;
      try {
        const nextSelected = camsOverride ?? selectedIdsRef.current;
        if (!nextSelected.length) {
          setSegmentsByCam({});
          setMarkers([]);
          setEventIntervals([]);
          setSegmentsLoaded(true);
          if (!opts?.merge) {
            viewport.resetToData(null, null, opts?.date ?? date);
          }
          return;
        }
        const useDate = opts?.date ?? date;
        const segKey = `playback:segments:${useDate ?? ''}:${opts?.from ?? ''}:${opts?.to ?? ''}:${nextSelected.join(',')}`;
        const evKey = `playback:events:${useDate ?? ''}:${opts?.from ?? ''}:${opts?.to ?? ''}:${nextSelected.join(',')}`;

        const cachedBatch = cacheGet<{ by_camera: Record<string, PlaybackSegment[]>; items: PlaybackSegment[] }>(segKey);
        const cachedEv = cacheGet<{ items: PlaybackEventInterval[]; legacy_markers?: PlaybackEventMarker[] }>(evKey);
        if (cachedBatch?.by_camera && cachedEv?.items) {
          const incoming: Record<string, PlaybackSegment[]> = { ...(cachedBatch.by_camera || {}) };
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
            const incomingMarkers = cachedEv.legacy_markers ?? [];
            if (!opts?.merge) return incomingMarkers;
            const byKey = new Map<string, PlaybackEventMarker>();
            for (const m of prev) byKey.set(`${m.ts}:${m.camera}:${m.type}`, m);
            for (const m of incomingMarkers) byKey.set(`${m.ts}:${m.camera}:${m.type}`, m);
            return Array.from(byKey.values()).sort((a, b) => a.ts - b.ts);
          });
          setEventIntervals((prev) => {
            if (!opts?.merge) return cachedEv.items;
            const byKey = new Map<string, PlaybackEventInterval>();
            for (const it of prev) byKey.set(`${it.start_ts}:${it.end_ts}:${it.camera}:${it.event_type}:${it.label}`, it);
            for (const it of cachedEv.items) byKey.set(`${it.start_ts}:${it.end_ts}:${it.camera}:${it.event_type}:${it.label}`, it);
            return Array.from(byKey.values()).sort((a, b) => a.start_ts - b.start_ts);
          });

          setSegmentsLoaded(true);
          if (!opts?.merge) {
            const target = initialT != null ? initialT : ctrl.getPosition();
            const snapped = allSegs.length ? snapPositionToPlayable(allSegs, target) : target;
            if (Math.abs(snapped - ctrl.getPosition()) > 0.5) ctrl.seek(snapped);
          }
          return;
        }

        if (isInitialLoad) {
          setSegmentsLoading(true);
          didSetSegmentsLoading = true;
        }

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

        cacheSet(segKey, batch, SEGMENTS_TTL_MS);
        cacheSet(evKey, ev, SEGMENTS_TTL_MS);

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
          const incomingMarkers = ev.legacy_markers ?? [];
          if (!opts?.merge) return incomingMarkers;
          const byKey = new Map<string, PlaybackEventMarker>();
          for (const m of prev) byKey.set(`${m.ts}:${m.camera}:${m.type}`, m);
          for (const m of incomingMarkers) byKey.set(`${m.ts}:${m.camera}:${m.type}`, m);
          return Array.from(byKey.values()).sort((a, b) => a.ts - b.ts);
        });
        setEventIntervals((prev) => {
          if (!opts?.merge) return ev.items;
          const byKey = new Map<string, PlaybackEventInterval>();
          for (const it of prev) byKey.set(`${it.start_ts}:${it.end_ts}:${it.camera}:${it.event_type}:${it.label}`, it);
          for (const it of ev.items) byKey.set(`${it.start_ts}:${it.end_ts}:${it.camera}:${it.event_type}:${it.label}`, it);
          return Array.from(byKey.values()).sort((a, b) => a.start_ts - b.start_ts);
        });
        setSegmentsLoaded(true);
        if (!opts?.merge) {
          const target = initialT != null ? initialT : ctrl.getPosition();
          const snapped = allSegs.length ? snapPositionToPlayable(allSegs, target) : target;
          if (Math.abs(snapped - ctrl.getPosition()) > 0.5) ctrl.seek(snapped);
        }
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
        if (didSetSegmentsLoading) setSegmentsLoading(false);
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
    const deepLinkForDate = initialT != null && dateFromUnixSec(initialT) === date ? initialT : null;
    void loadSegments(selectedIds, initialSegmentWindow(date, deepLinkForDate));
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
      setSeekSettling(true);
      if (seekSettleTimerRef.current != null) window.clearTimeout(seekSettleTimerRef.current);
      seekSettleTimerRef.current = window.setTimeout(() => {
        setSeekSettling(false);
        seekSettleTimerRef.current = null;
      }, SEEK_SETTLE_HOLD_MS);
      ensureAdjacentLoad(sec - SEEK_LOAD_HALF_SEC, sec + SEEK_LOAD_HALF_SEC);
    },
    [ctrl, ensureAdjacentLoad],
  );

  useEffect(() => {
    return () => {
      if (seekSettleTimerRef.current != null) window.clearTimeout(seekSettleTimerRef.current);
    };
  }, []);

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
  const timelineEventIntervals = useMemo(() => {
    const { start, end } = dayBoundsLocal(date);
    return eventIntervals.filter((it) => it.end_ts >= start && it.start_ts < end);
  }, [eventIntervals, date]);
  const eventIntervalsByCamera = useMemo(() => {
    const out: Record<string, PlaybackEventInterval[]> = {};
    for (const id of selectedIds) out[id] = [];
    for (const it of eventIntervals) {
      if (it.camera && out[it.camera]) out[it.camera].push(it);
    }
    return out;
  }, [eventIntervals, selectedIds]);
  const effectiveCols = mode === 'fit' ? fitColsForCount(selectedIds.length) : cols;
  const positionLabel = formatPlaybackDateTime(ctrl.positionSec);
  const detectionsReady = !detectionIndex.loading;

  let gridEmpty: string | null = null;
  if (camerasLoading) gridEmpty = t('playback.loadingCamerasGrid');
  else if (!cameras.length) gridEmpty = t('playback.noCamerasForDate');
  else if (!selectedIds.length) gridEmpty = t('playback.selectCameras');
  else if (segmentsLoading || (!segmentsLoaded && cameras.length > 0)) gridEmpty = t('playback.loadingSegment');

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
              scrubbing={seekSettling}
              detectionItems={detectionIndex.byCamera[expandedCamera.id] ?? []}
              globalDetectionTs={detectionIndex.globalTs}
              eventIntervals={eventIntervalsByCamera[expandedCamera.id] ?? []}
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
              scrubbing={seekSettling}
              detectionByCamera={detectionIndex.byCamera}
              globalDetectionTs={detectionIndex.globalTs}
              eventIntervalsByCamera={eventIntervalsByCamera}
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
            eventIntervals={timelineEventIntervals}
            onSeek={seek}
            onViewChange={onViewChange}
            onPanningChange={setTimelinePanning}
          />
        </div>
      </div>
    </section>
  );
}
