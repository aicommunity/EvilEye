import { useEffect, useRef } from 'react';

export function PlaybackGrid({
  cameras,
  mediaByCam,
  positionSec,
  playing,
  speed,
}: {
  cameras: string[];
  mediaByCam: Record<string, string | null>;
  positionSec: number;
  playing: boolean;
  speed: number;
}) {
  if (!cameras.length) return <p className="empty">Выберите камеры.</p>;
  return (
    <div className="camera-group-grid" style={{ gridTemplateColumns: `repeat(${Math.min(cameras.length, 2)}, 1fr)` }}>
      {cameras.map((id) => (
        <PlaybackCell key={id} id={id} src={mediaByCam[id]} positionSec={positionSec} playing={playing} speed={speed} />
      ))}
    </div>
  );
}

function PlaybackCell({
  id,
  src,
  positionSec,
  playing,
  speed,
}: {
  id: string;
  src: string | null;
  positionSec: number;
  playing: boolean;
  speed: number;
}) {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const v = ref.current;
    if (!v || !src) return;
    // Best-effort sync: treat positionSec as absolute unix; video is relative — use modulo of duration if available
    if (v.duration && Number.isFinite(v.duration)) {
      const local = positionSec % v.duration;
      if (Math.abs(v.currentTime - local) > 0.5) v.currentTime = local;
    }
  }, [positionSec, src]);

  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    v.playbackRate = speed;
    if (playing) void v.play().catch(() => null);
    else v.pause();
  }, [playing, speed]);

  return (
    <article className="camera-card">
      <div className="camera-card-head">
        <span className="run-name">{id}</span>
      </div>
      {src ? <video ref={ref} src={src} controls style={{ width: '100%' }} /> : <div className="camera-preview-empty">Нет сегмента</div>}
    </article>
  );
}
