import { useEffect, useRef } from 'react';

export type PlaybackMediaSlot = {
  url: string | null;
  startTs: number;
  endTs: number;
};

export function PlaybackGrid({
  cameras,
  mediaByCam,
  positionSec,
  playing,
  speed,
}: {
  cameras: string[];
  mediaByCam: Record<string, PlaybackMediaSlot | null>;
  positionSec: number;
  playing: boolean;
  speed: number;
}) {
  if (!cameras.length) return <p className="empty">Выберите камеры.</p>;
  return (
    <div className="camera-group-grid" style={{ gridTemplateColumns: `repeat(${Math.min(cameras.length, 2)}, 1fr)` }}>
      {cameras.map((id) => (
        <PlaybackCell
          key={id}
          id={id}
          slot={mediaByCam[id]}
          positionSec={positionSec}
          playing={playing}
          speed={speed}
        />
      ))}
    </div>
  );
}

function PlaybackCell({
  id,
  slot,
  positionSec,
  playing,
  speed,
}: {
  id: string;
  slot: PlaybackMediaSlot | null | undefined;
  positionSec: number;
  playing: boolean;
  speed: number;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  const src = slot?.url ?? null;

  useEffect(() => {
    const v = ref.current;
    if (!v || !src || !slot) return;
    const local = Math.max(0, positionSec - slot.startTs);
    if (Math.abs(v.currentTime - local) > 0.4) {
      try {
        v.currentTime = local;
      } catch {
        /* ignore seek race */
      }
    }
  }, [positionSec, src, slot]);

  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    v.playbackRate = speed;
    if (playing) void v.play().catch(() => null);
    else v.pause();
  }, [playing, speed, src]);

  return (
    <article className="camera-card">
      <div className="camera-card-head">
        <span className="run-name">{id}</span>
      </div>
      {src ? (
        <video ref={ref} src={src} controls style={{ width: '100%' }} />
      ) : (
        <div className="camera-preview-empty">Нет сегмента</div>
      )}
    </article>
  );
}
