import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { playbackApi, stateApi, type PlaybackCamera, type PlaybackEventMarker, type PlaybackSegment } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';
import { Timeline } from './Timeline';
import { PlaybackGrid } from './PlaybackGrid';
import { usePlaybackController } from './usePlaybackController';
import { usePlaybackLayout } from './usePlaybackLayout';

const MAX_PLAYBACK_CAMS = 4;

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

export function PlaybackPage() {
  const [params] = useSearchParams();
  const { showError } = useToast();
  const { t } = useI18n();
  const [date, setDate] = useState(today());
  const [runId, setRunId] = useState<number | null>(null);
  const [cameras, setCameras] = useState<PlaybackCamera[]>([]);
  const [camerasLoading, setCamerasLoading] = useState(false);
  const { cols, setCols, selectedIds, setSelectedIds } = usePlaybackLayout();
  const [segmentsByCam, setSegmentsByCam] = useState<Record<string, PlaybackSegment[]>>({});
  const [markers, setMarkers] = useState<PlaybackEventMarker[]>([]);
  const [segmentsLoaded, setSegmentsLoaded] = useState(false);
  const initialT = parseDeepLinkTime(params.get('t'));
  const ctrl = usePlaybackController(initialT);
  const urlCamera = params.get('camera');

  useEffect(() => {
    void stateApi.runs('current').then((res) => {
      const items = Array.isArray(res) ? res : res.items ?? [];
      const running = items.find((r) => r.state === 'running') ?? items[0];
      if (running?.id) setRunId(running.id);
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setCamerasLoading(true);
      try {
        const camRes = await playbackApi.cameras(date, runId);
        if (cancelled) return;
        setCameras(camRes.items);
        const ids = new Set(camRes.items.map((c) => c.id));
        setSelectedIds((prev) => {
          const kept = prev.filter((id) => ids.has(id));
          if (kept.length) return kept.slice(0, MAX_PLAYBACK_CAMS);
          if (urlCamera && ids.has(urlCamera)) return [urlCamera];
          return camRes.items.slice(0, Math.min(2, camRes.items.length)).map((c) => c.id);
        });
        setSegmentsByCam({});
        setMarkers([]);
        setSegmentsLoaded(false);
      } catch (e) {
        if (!cancelled) showError(e instanceof Error ? e.message : t('playback.unavailable'));
      } finally {
        if (!cancelled) setCamerasLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [date, runId, showError, t, urlCamera, setSelectedIds]);

  const loadSegments = useCallback(async (camsOverride?: string[]) => {
    try {
      let nextSelected = camsOverride ?? selectedIds;
      if (nextSelected.length > MAX_PLAYBACK_CAMS) {
        nextSelected = nextSelected.slice(0, MAX_PLAYBACK_CAMS);
        setSelectedIds(nextSelected);
      }
      if (!nextSelected.length) {
        setSegmentsByCam({});
        setMarkers([]);
        setSegmentsLoaded(true);
        return;
      }
      const batch = await playbackApi.segmentsBatch(nextSelected, undefined, undefined, date);
      const segMap: Record<string, PlaybackSegment[]> = { ...(batch.by_camera || {}) };
      for (const id of nextSelected) {
        if (!segMap[id]) segMap[id] = [];
      }
      setSegmentsByCam(segMap);
      const allSegs = Object.values(segMap).flat();
      const from = allSegs.length ? Math.min(...allSegs.map((s) => s.start_ts)) : undefined;
      const to = allSegs.length ? Math.max(...allSegs.map((s) => s.end_ts)) : undefined;
      ctrl.setRange(from ?? null, to ?? null);
      const ev = await playbackApi.events(from, to, undefined, date, nextSelected);
      setMarkers(ev.items);
      setSegmentsLoaded(true);
      if (initialT != null) ctrl.seek(initialT);
    } catch (e) {
      showError(e instanceof Error ? e.message : t('playback.unavailable'));
    }
  }, [date, initialT, selectedIds, setSelectedIds, showError, t, ctrl]);

  useEffect(() => {
    if (!selectedIds.length || camerasLoading) return;
    void loadSegments(selectedIds);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on date/selection only
  }, [date, selectedIds, camerasLoading]);

  const toggleCamera = (id: string) => {
    const on = selectedIds.includes(id);
    let next = on ? selectedIds.filter((x) => x !== id) : [...selectedIds, id];
    if (!on && next.length > MAX_PLAYBACK_CAMS) {
      next = [...selectedIds.slice(1), id].slice(0, MAX_PLAYBACK_CAMS);
    }
    setSelectedIds(next);
  };

  const cameraDefs = useMemo(() => Object.fromEntries(cameras.map((c) => [c.id, c])), [cameras]);
  const allSegments = useMemo(() => Object.values(segmentsByCam).flat(), [segmentsByCam]);

  let gridEmpty: string | null = null;
  if (camerasLoading) gridEmpty = t('playback.loadingCamerasGrid');
  else if (!cameras.length) gridEmpty = t('playback.noCamerasForDate');
  else if (!selectedIds.length) gridEmpty = t('playback.selectCameras');
  else if (!segmentsLoaded) gridEmpty = t('playback.loadingCamerasGrid');

  return (
    <section className="panel active playback-page">
      <div className="card playback-card">
        <div className="toolbar" style={{ justifyContent: 'space-between', flexWrap: 'wrap' }}>
          <div>
            <h2 style={{ margin: 0 }}>{t('playback.title')}</h2>
            <p className="hint">{t('playback.hint')}</p>
          </div>
          <div className="toolbar">
            <input type="date" className="search-input" value={date} onChange={(e) => setDate(e.target.value)} />
            {[1, 2, 4].map((n) => (
              <Button key={n} size="sm" variant={cols === n ? 'primary' : 'outline'} onClick={() => setCols(n)}>
                {n}
              </Button>
            ))}
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
              cols={cols}
              segmentsByCam={segmentsByCam}
              getPosition={ctrl.getPosition}
              playing={ctrl.playing}
              speed={ctrl.speed}
            />
          )}
        </div>
        <div className="playback-timeline-footer">
          <Timeline
            from={ctrl.fromSec}
            to={ctrl.toSec}
            position={ctrl.positionSec}
            markers={markers}
            segments={allSegments}
            onSeek={ctrl.seek}
          />
        </div>
      </div>
    </section>
  );
}
