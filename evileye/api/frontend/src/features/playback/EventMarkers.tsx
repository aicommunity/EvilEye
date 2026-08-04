import type { PlaybackEventMarker } from '../../api';

/** Event ticks for the playback timeline (ported from EventMarkersWidget). */
export function EventMarkers({
  markers,
  from,
  to,
  onSelect,
}: {
  markers: PlaybackEventMarker[];
  from: number;
  to: number;
  onSelect?: (marker: PlaybackEventMarker) => void;
}) {
  const span = to - from;
  if (span <= 0) return null;
  return (
    <>
      {markers.map((m, i) => {
        const left = ((m.ts - from) / span) * 100;
        if (left < 0 || left > 100) return null;
        return (
          <button
            key={`${m.row_key ?? m.ts}-${i}`}
            type="button"
            title={`${m.type} · ${m.camera} @ ${new Date(m.ts * 1000).toLocaleString('ru-RU')}`}
            aria-label={`marker-${m.type}`}
            onClick={(e) => {
              e.stopPropagation();
              onSelect?.(m);
            }}
            style={{
              position: 'absolute',
              left: `${left}%`,
              top: 4,
              width: 6,
              height: 40,
              padding: 0,
              border: 'none',
              background: m.type === 'mp4' ? '#f59e0b' : '#ef4444',
              transform: 'translateX(-50%)',
              cursor: 'pointer',
              borderRadius: 2,
            }}
          />
        );
      })}
    </>
  );
}
