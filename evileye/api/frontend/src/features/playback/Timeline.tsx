import type { PlaybackEventMarker } from '../../api';

export function Timeline({
  from,
  to,
  position,
  markers,
  onSeek,
}: {
  from: number | null;
  to: number | null;
  position: number;
  markers: PlaybackEventMarker[];
  onSeek: (sec: number) => void;
}) {
  if (from == null || to == null || to <= from) {
    return <p className="hint">Загрузите сегменты для отображения таймлайна.</p>;
  }
  const span = to - from;
  const pct = ((position - from) / span) * 100;

  return (
    <div
      className="playback-timeline"
      style={{
        position: 'relative',
        height: 48,
        margin: '1rem 0',
        background: 'var(--bg-card-hover)',
        borderRadius: 8,
        border: '1px solid var(--border)',
        cursor: 'pointer',
      }}
      onClick={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width;
        onSeek(from + x * span);
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: 0,
          width: `${Math.max(0, Math.min(100, pct))}%`,
          background: 'rgba(59,130,246,0.35)',
          borderRadius: 8,
        }}
      />
      {markers.map((m, i) => {
        const left = ((m.ts - from) / span) * 100;
        if (left < 0 || left > 100) return null;
        return (
          <span
            key={i}
            title={`${m.type} @ ${new Date(m.ts * 1000).toLocaleString('ru-RU')}`}
            style={{
              position: 'absolute',
              left: `${left}%`,
              top: 4,
              width: 4,
              height: 40,
              background: '#ef4444',
              transform: 'translateX(-50%)',
            }}
          />
        );
      })}
    </div>
  );
}

export { EventMarkers } from './EventMarkers';
