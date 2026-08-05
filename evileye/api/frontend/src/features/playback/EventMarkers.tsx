import { useState } from 'react';
import type { PlaybackEventMarker } from '../../api';
import { useI18n } from '../../i18n';

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
  const { localeTag } = useI18n();
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
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
        const clusterKey = `${c.leftPct}-${i}`;
        const title =
          c.count > 1
            ? `${c.count} events @ ${new Date(primary.ts * 1000).toLocaleString(localeTag)}`
            : `${primary.type} · ${primary.camera} @ ${new Date(primary.ts * 1000).toLocaleString(localeTag)}`;
        const expanded = expandedKey === clusterKey;
        return (
          <div key={clusterKey} style={{ position: 'absolute', left: `${c.leftPct}%`, top: 4, transform: 'translateX(-50%)', zIndex: expanded ? 5 : 1 }}>
            <button
              type="button"
              data-timeline-marker
              title={title}
              aria-label={`marker-cluster-${c.count}`}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                if (c.count > 1) {
                  setExpandedKey(expanded ? null : clusterKey);
                  return;
                }
                onSelect?.(primary);
              }}
              style={{
                minWidth: c.count > 1 ? 14 : 6,
                height: 40,
                padding: c.count > 1 ? '0 2px' : 0,
                border: 'none',
                background: c.type === 'mp4' ? '#f59e0b' : '#ef4444',
                color: '#fff',
                fontSize: 9,
                lineHeight: '40px',
                cursor: 'pointer',
                borderRadius: 2,
              }}
            >
              {c.count > 1 ? c.count : null}
            </button>
            {expanded ? (
              <ul
                role="listbox"
                style={{
                  position: 'absolute',
                  top: 44,
                  left: '50%',
                  transform: 'translateX(-50%)',
                  margin: 0,
                  padding: '4px 0',
                  listStyle: 'none',
                  background: 'var(--bg-card, #1e293b)',
                  border: '1px solid var(--border, #334155)',
                  borderRadius: 6,
                  minWidth: 180,
                  maxHeight: 180,
                  overflow: 'auto',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
                }}
                onClick={(e) => e.stopPropagation()}
              >
                {c.markers.map((m, mi) => (
                  <li key={`${m.row_key ?? m.ts}-${mi}`}>
                    <button
                      type="button"
                      onClick={() => {
                        setExpandedKey(null);
                        onSelect?.(m);
                      }}
                      style={{
                        display: 'block',
                        width: '100%',
                        textAlign: 'left',
                        border: 'none',
                        background: 'transparent',
                        color: 'inherit',
                        padding: '6px 10px',
                        cursor: 'pointer',
                        fontSize: 12,
                      }}
                    >
                      {m.type} · {m.camera}
                      <br />
                      <span style={{ opacity: 0.7 }}>{new Date(m.ts * 1000).toLocaleString(localeTag)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        );
      })}
    </>
  );
}
