import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { playbackApi, type PlaybackCamera, type PlaybackEventMarker, type PlaybackSegment } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';
import { Timeline } from './Timeline';
import { PlaybackGrid, type PlaybackMediaSlot } from './PlaybackGrid';
import { usePlaybackController } from './usePlaybackController';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function PlaybackPage() {
  const [params] = useSearchParams();
  const { showError } = useToast();
  const { t } = useI18n();
  const [date, setDate] = useState(today());
  const [cameras, setCameras] = useState<PlaybackCamera[]>([]);
  const [camerasLoading, setCamerasLoading] = useState(false);
  const [selected, setSelected] = useState<string[]>(() => {
    const c = params.get('camera');
    return c ? [c] : [];
  });
  const [segmentsByCam, setSegmentsByCam] = useState<Record<string, PlaybackSegment[]>>({});
  const [markers, setMarkers] = useState<PlaybackEventMarker[]>([]);
  const [segmentsLoaded, setSegmentsLoaded] = useState(false);
  const initialT = Number(params.get('t') || 0) || null;
  const ctrl = usePlaybackController(initialT);
  const urlCamera = params.get('camera');

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setCamerasLoading(true);
      try {
        const camRes = await playbackApi.cameras(date);
        if (cancelled) return;
        setCameras(camRes.items);
        setSelected((prev) => {
          const ids = new Set(camRes.items.map((c) => c.id));
          const kept = prev.filter((id) => ids.has(id));
          if (kept.length) return kept;
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
  }, [date, showError, urlCamera]);

  const loadSegments = async (camsOverride?: string[]) => {
    try {
      const MAX_PLAYBACK_CAMS = 4;
      let nextSelected = camsOverride ?? selected;
      if (nextSelected.length > MAX_PLAYBACK_CAMS) {
        nextSelected = nextSelected.slice(0, MAX_PLAYBACK_CAMS);
        setSelected(nextSelected);
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
      const ev = await playbackApi.events(from, to, nextSelected[0], date);
      setMarkers(ev.items);
      setSegmentsLoaded(true);
    } catch (e) {
      showError(e instanceof Error ? e.message : t('playback.unavailable'));
    }
  };

  const mediaByCam = useMemo(() => {
    const result: Record<string, PlaybackMediaSlot | null> = {};
    for (const id of selected) {
      const segs = segmentsByCam[id] ?? [];
      const active =
        segs.find((s) => ctrl.positionSec >= s.start_ts && ctrl.positionSec <= s.end_ts) ?? segs[0];
      result[id] = active
        ? {
            url: playbackApi.mediaUrl(active.path),
            startTs: active.start_ts,
            endTs: active.end_ts,
          }
        : null;
    }
    return result;
  }, [selected, segmentsByCam, ctrl.positionSec]);

  const toggleCamera = (id: string) => {
    const on = selected.includes(id);
    const MAX_PLAYBACK_CAMS = 4;
    let next = on ? selected.filter((x) => x !== id) : [...selected, id];
    if (!on && next.length > MAX_PLAYBACK_CAMS) {
      next = [...selected.slice(1), id].slice(0, MAX_PLAYBACK_CAMS);
    }
    setSelected(next);
    if (segmentsLoaded) void loadSegments(next);
  };

  let gridEmpty: string | null = null;
  if (camerasLoading) gridEmpty = t('playback.loadingCamerasGrid');
  else if (!cameras.length) gridEmpty = t('playback.noCamerasForDate');
  else if (!selected.length) gridEmpty = t('playback.selectCameras');
  else if (!segmentsLoaded) gridEmpty = t('playback.pressLoad');

  return (
    <section className="panel active">
      <div className="card">
        <h2>{t('playback.title')}</h2>
        <p className="hint">{t('playback.hint')}</p>
        <div className="toolbar">
          <input type="date" className="search-input" value={date} onChange={(e) => setDate(e.target.value)} />
          <Button variant="primary" onClick={() => void loadSegments()} disabled={!selected.length}>
            {t('playback.load')}
          </Button>
          <Button size="sm" variant={ctrl.playing ? 'danger' : 'success'} onClick={() => ctrl.setPlaying(!ctrl.playing)}>
            {ctrl.playing ? t('playback.pause') : t('playback.play')}
          </Button>
          {[0.5, 1, 2, 4].map((s) => (
            <Button key={s} size="sm" variant={ctrl.speed === s ? 'primary' : 'outline'} onClick={() => ctrl.setSpeed(s)}>
              {s}x
            </Button>
          ))}
        </div>
        <div className="toolbar" style={{ flexWrap: 'wrap' }}>
          {camerasLoading ? <span className="hint">{t('playback.loadingCameras')}</span> : null}
          {!camerasLoading && !cameras.length ? <span className="hint">{t('playback.noCameras')}</span> : null}
          {cameras.map((c) => {
            const on = selected.includes(c.id);
            return (
              <Button key={c.id} size="sm" variant={on ? 'primary' : 'outline'} onClick={() => toggleCamera(c.id)}>
                {c.name}
              </Button>
            );
          })}
        </div>
        <Timeline
          from={ctrl.fromSec}
          to={ctrl.toSec}
          position={ctrl.positionSec}
          markers={markers}
          onSeek={ctrl.seek}
        />
        {gridEmpty ? (
          <p className="empty">{gridEmpty}</p>
        ) : (
          <PlaybackGrid
            cameras={selected}
            mediaByCam={mediaByCam}
            positionSec={ctrl.positionSec}
            playing={ctrl.playing}
            speed={ctrl.speed}
          />
        )}
      </div>
    </section>
  );
}
