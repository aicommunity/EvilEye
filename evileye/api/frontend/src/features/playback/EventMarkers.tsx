import type { PlaybackEventMarker } from '../../api';

type Cluster = {
  leftPct: number;
  count: number;
  markers: PlaybackEventMarker[];
  type: string;
};

/** Event ticks for the playback timeline — clustered by pixel column. */
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

  const bucketPct = 0.4; // ~2px on a 500px timeline
  const buckets = new Map<number, Cluster>();
  for (const m of markers) {
    const left = ((m.ts - from) / span) * 100;
    if (left < 0 || left > 100) continue;
    const key = Math.round(left / bucketPct);
    const existing = buckets.get(key);
    if (existing) {
      existing.count += 1;
      existing.markers.push(m);
    } else {
      buckets.set(key, {
        leftPct: key * bucketPct,
        count: 1,
        markers: [m],
        type: m.type,
      });
    }
  }

  const clusters = Array.from(buckets.values())
    .sort((a, b) => a.leftPct - b.leftPct)
    .slice(0, 200);

  return (
    <>
      {clusters.map((c, i) => {
        const primary = c.markers[0];
        const title =
          c.count > 1
            ? `${c.count} events @ ${new Date(primary.ts * 1000).toLocaleString('ru-RU')}`
            : `${primary.type} · ${primary.camera} @ ${new Date(primary.ts * 1000).toLocaleString('ru-RU')}`;
        return (
          <button
            key={`${c.leftPct}-${i}`}
            type="button"
            title={title}
            aria-label={`marker-cluster-${c.count}`}
            onClick={(e) => {
              e.stopPropagation();
              onSelect?.(primary);
            }}
            style={{
              position: 'absolute',
              left: `${c.leftPct}%`,
              top: 4,
              minWidth: c.count > 1 ? 14 : 6,
              height: 40,
              padding: c.count > 1 ? '0 2px' : 0,
              border: 'none',
              background: c.type === 'mp4' ? '#f59e0b' : '#ef4444',
              color: '#fff',
              fontSize: 9,
              lineHeight: '40px',
              transform: 'translateX(-50%)',
              cursor: 'pointer',
              borderRadius: 2,
            }}
          >
            {c.count > 1 ? c.count : null}
          </button>
        );
      })}
    </>
  );
}
