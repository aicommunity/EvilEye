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
import { usePlaybackController } from './usePlaybackController';
import { usePlaybackLayout } from './usePlaybackLayout';
import { useTimelineViewport } from './useTimelineViewport';
import { fitColsForCount } from '../layout/fitGrid';
import { localDateString, mergeSegments } from './timelineMath';

function today(): string {
  const d = new Date();
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
  const initialT = parseDeepLinkTime(params.get('t'));
  const ctrl = usePlaybackController(initialT);
  const viewport = useTimelineViewport();
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
        const useDate = opts?.merge ? undefined : (opts?.date ?? date);
        const segKey = `playback:segments:${useDate ?? ''}:${opts?.from ?? ''}:${opts?.to ?? ''}:${nextSelected.join(',')}`;
        const evKey = `playback:events:${useDate ?? ''}:${opts?.from ?? ''}:${opts?.to ?? ''}:${nextSelected.join(',')}`;

        const [batch, ev] = await Promise.all([
          playbackApi.segmentsBatch(nextSelected, opts?.from, opts?.to, useDate, { signal: ac.signal }),
          playbackApi.events(opts?.from, opts?.to, undefined, opts?.merge ? undefined : useDate, nextSelected, {
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
        if (isAbortError(e)) return;
        showError(e instanceof Error ? e.message : t('playback.unavailable'));
      }
    },
    [date, initialT, showError, ctrl, viewport],
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
    void loadSegments(selectedIds);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on date/selection only
  }, [date, selectedIds, camerasLoading]);

  const ensureAdjacentLoad = useCallback(
    (vf: number, vt: number) => {
      const { needFrom, needTo, needed } = viewport.needsLoad(vf, vt);
      if (!needed) return;
      if (loadTimerRef.current) window.clearTimeout(loadTimerRef.current);
      loadTimerRef.current = window.setTimeout(() => {
        void loadSegments(selectedIdsRef.current, {
          from: needFrom,
          to: needTo,
          merge: true,
        });
      }, 250);
    },
    [loadSegments, viewport],
  );

  const onViewChange = useCallback(
    (vf: number, vt: number) => {
      viewport.setView(vf, vt);
      ensureAdjacentLoad(vf, vt);
      const centerDate = localDateString((vf + vt) / 2);
      if (centerDate !== date) {
        dateChangeSourceRef.current = 'viewport';
        setDate(centerDate);
      }
    },
    [viewport, ensureAdjacentLoad, date],
  );

  const toggleCamera = (id: string) => {
    const on = selectedIds.includes(id);
    const next = on ? selectedIds.filter((x) => x !== id) : [...selectedIds, id];
    setSelectedIds(next);
  };

  const cameraDefs = useMemo(() => Object.fromEntries(cameras.map((c) => [c.id, c])), [cameras]);
  const allSegments = useMemo(() => Object.values(segmentsByCam).flat(), [segmentsByCam]);
  const effectiveCols = mode === 'fit' ? fitColsForCount(selectedIds.length) : cols;

  let gridEmpty: string | null = null;
  if (camerasLoading) gridEmpty = t('playback.loadingCamerasGrid');
  else if (!cameras.length) gridEmpty = t('playback.noCamerasForDate');
  else if (!selectedIds.length) gridEmpty = t('playback.selectCameras');
  else if (!segmentsLoaded) gridEmpty = t('playback.loadingCamerasGrid');

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
            <Button size="sm" variant={ctrl.playing ? 'danger' : 'success'} onClick={() => ctrl.setPlaying(!ctrl.playing)}>
              {ctrl.playing ? t('playback.pause') : t('playback.play')}
            </Button>
            {[0.5, 1, 2, 4].map((s) => (
              <Button key={s} size="sm" variant={ctrl.speed === s ? 'primary' : 'outline'} onClick={() => ctrl.setSpeed(s)}>
                {s}x
              </Button>
            ))}
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
        <div className="playback-main">
          {gridEmpty ? (
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
            markers={markers}
            segments={allSegments}
            onSeek={ctrl.seek}
            onViewChange={onViewChange}
          />
        </div>
      </div>
    </section>
  );
}
