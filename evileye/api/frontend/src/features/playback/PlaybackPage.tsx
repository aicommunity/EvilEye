import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { playbackApi, type PlaybackCamera, type PlaybackEventMarker, type PlaybackSegment } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { Timeline } from './Timeline';
import { PlaybackGrid } from './PlaybackGrid';
import { usePlaybackController } from './usePlaybackController';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function PlaybackPage() {
  const [params] = useSearchParams();
  const { showError } = useToast();
  const [date, setDate] = useState(today());
  const [cameras, setCameras] = useState<PlaybackCamera[]>([]);
  const [selected, setSelected] = useState<string[]>(() => {
    const c = params.get('camera');
    return c ? [c] : [];
  });
  const [segmentsByCam, setSegmentsByCam] = useState<Record<string, PlaybackSegment[]>>({});
  const [markers, setMarkers] = useState<PlaybackEventMarker[]>([]);
  const initialT = Number(params.get('t') || 0) || null;
  const ctrl = usePlaybackController(initialT);

  const load = async () => {
    try {
      const camRes = await playbackApi.cameras(date);
      setCameras(camRes.items);
      const nextSelected = selected.length ? selected : camRes.items.slice(0, 2).map((c) => c.id);
      setSelected(nextSelected);
      const segMap: Record<string, PlaybackSegment[]> = {};
      for (const id of nextSelected) {
        const seg = await playbackApi.segments(id);
        segMap[id] = seg.items;
      }
      setSegmentsByCam(segMap);
      const allSegs = Object.values(segMap).flat();
      const from = allSegs.length ? Math.min(...allSegs.map((s) => s.start_ts)) : undefined;
      const to = allSegs.length ? Math.max(...allSegs.map((s) => s.end_ts)) : undefined;
      ctrl.setRange(from ?? null, to ?? null);
      const ev = await playbackApi.events(from, to);
      setMarkers(ev.items);
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Playback недоступен');
    }
  };

  const mediaByCam = useMemo(() => {
    const result: Record<string, string | null> = {};
    for (const id of selected) {
      const segs = segmentsByCam[id] ?? [];
      const active = segs.find((s) => ctrl.positionSec >= s.start_ts && ctrl.positionSec <= s.end_ts) ?? segs[0];
      result[id] = active ? playbackApi.mediaUrl(active.path) : null;
    }
    return result;
  }, [selected, segmentsByCam, ctrl.positionSec]);

  return (
    <section className="panel active">
      <div className="card">
        <h2>Playback</h2>
        <p className="hint">Таймлайн записей Streams с маркерами событий</p>
        <div className="toolbar">
          <input type="date" className="search-input" value={date} onChange={(e) => setDate(e.target.value)} />
          <Button variant="primary" onClick={() => void load()}>
            Загрузить
          </Button>
          <Button size="sm" variant={ctrl.playing ? 'danger' : 'success'} onClick={() => ctrl.setPlaying(!ctrl.playing)}>
            {ctrl.playing ? 'Pause' : 'Play'}
          </Button>
          {[0.5, 1, 2, 4].map((s) => (
            <Button key={s} size="sm" variant={ctrl.speed === s ? 'primary' : 'outline'} onClick={() => ctrl.setSpeed(s)}>
              {s}x
            </Button>
          ))}
        </div>
        <div className="toolbar" style={{ flexWrap: 'wrap' }}>
          {cameras.map((c) => {
            const on = selected.includes(c.id);
            return (
              <Button
                key={c.id}
                size="sm"
                variant={on ? 'primary' : 'outline'}
                onClick={() =>
                  setSelected((prev) => (on ? prev.filter((x) => x !== c.id) : [...prev, c.id]))
                }
              >
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
        <PlaybackGrid cameras={selected} mediaByCam={mediaByCam} positionSec={ctrl.positionSec} playing={ctrl.playing} speed={ctrl.speed} />
      </div>
    </section>
  );
}
