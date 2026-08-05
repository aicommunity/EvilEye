import type { PlaybackEventMarker, PlaybackSegment } from '../../api';
import { useI18n } from '../../i18n';
import { EventMarkers } from './EventMarkers';

export function Timeline({
  from,
  to,
  position,
  markers,
  segments = [],
  onSeek,
}: {
  from: number | null;
  to: number | null;
  position: number;
  markers: PlaybackEventMarker[];
  segments?: PlaybackSegment[];
  onSeek: (sec: number) => void;
}) {
  const { t } = useI18n();
  if (from == null || to == null || to <= from) {
    return <p className="hint">{t('playback.timelineEmpty')}</p>;
  }
  const span = to - from;
  const pct = ((position - from) / span) * 100;

  return (
    <div
      className="playback-timeline playback-timeline-segments"
      style={{
        position: 'relative',
        height: 120,
        margin: '0',
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
      {segments.map((seg) => {
        const left = ((seg.start_ts - from) / span) * 100;
        const width = ((seg.end_ts - seg.start_ts) / span) * 100;
        if (width <= 0) return null;
        return (
          <div
            key={seg.path}
            className="timeline-segment-block"
            style={{
              position: 'absolute',
              left: `${Math.max(0, left)}%`,
              width: `${Math.min(100 - left, width)}%`,
              top: '20%',
              height: '60%',
              background: 'rgba(59, 130, 246, 0.45)',
              borderRadius: 4,
              border: '1px solid rgba(59, 130, 246, 0.7)',
            }}
            onClick={(e) => {
              e.stopPropagation();
              onSeek(seg.start_ts);
            }}
          />
        );
      })}
      <div
        className="timeline-playhead"
        style={{
          position: 'absolute',
          left: `${Math.max(0, Math.min(100, pct))}%`,
          top: 0,
          bottom: 0,
          width: 2,
          background: 'var(--accent)',
          pointerEvents: 'none',
        }}
      />
      <EventMarkers markers={markers} from={from} to={to} onSelect={(m) => onSeek(m.ts)} />
    </div>
  );
}

export { EventMarkers } from './EventMarkers';
