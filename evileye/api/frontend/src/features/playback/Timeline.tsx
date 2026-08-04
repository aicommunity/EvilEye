import type { PlaybackEventMarker } from '../../api';
import { useI18n } from '../../i18n';
import { EventMarkers } from './EventMarkers';

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
  const { t } = useI18n();
  if (from == null || to == null || to <= from) {
    return <p className="hint">{t('playback.timelineEmpty')}</p>;
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
      <EventMarkers markers={markers} from={from} to={to} onSelect={(m) => onSeek(m.ts)} />
    </div>
  );
}

export { EventMarkers } from './EventMarkers';
