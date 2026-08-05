import type { PlaybackEventMarker, PlaybackSegment } from '../../api';
import { useI18n } from '../../i18n';
import { EventMarkers } from './EventMarkers';

const TICK_STEPS_SEC = [60, 300, 900, 1800, 3600, 7200, 14400, 21600, 43200, 86400];

/** Build ~6–10 nicely spaced unix-second ticks in [from, to]. */
export function buildTimelineTicks(from: number, to: number): number[] {
  const span = to - from;
  if (!(span > 0)) return [];
  let step = TICK_STEPS_SEC[TICK_STEPS_SEC.length - 1];
  for (const candidate of TICK_STEPS_SEC) {
    const count = span / candidate;
    if (count <= 10) {
      step = candidate;
      break;
    }
  }
  // Prefer at least ~4 ticks when span allows.
  for (const candidate of TICK_STEPS_SEC) {
    if (candidate > step) break;
    const count = span / candidate;
    if (count >= 4 && count <= 10) {
      step = candidate;
    }
  }
  const first = Math.ceil(from / step) * step;
  const ticks: number[] = [];
  for (let ts = first; ts <= to + 1e-6; ts += step) {
    if (ts >= from - 1e-6 && ts <= to + 1e-6) ticks.push(ts);
  }
  if (!ticks.length || ticks[0] > from + step * 0.25) {
    ticks.unshift(from);
  }
  if (ticks[ticks.length - 1] < to - step * 0.25) {
    ticks.push(to);
  }
  // Dedupe near-duplicates at ends
  const out: number[] = [];
  for (const ts of ticks) {
    if (!out.length || Math.abs(ts - out[out.length - 1]) > step * 0.2) out.push(ts);
  }
  return out;
}

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
  const { t, localeTag } = useI18n();
  if (from == null || to == null || to <= from) {
    return <p className="hint">{t('playback.timelineEmpty')}</p>;
  }
  const span = to - from;
  const pct = ((position - from) / span) * 100;
  const ticks = buildTimelineTicks(from, to);

  return (
    <div
      className="playback-timeline playback-timeline-segments"
      style={{
        position: 'relative',
        height: 148,
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
      <div className="timeline-ticks" aria-hidden>
        {ticks.map((ts) => {
          const left = ((ts - from) / span) * 100;
          const edge =
            left < 3 ? 'timeline-tick-label--start' : left > 97 ? 'timeline-tick-label--end' : '';
          return (
            <div key={ts} className="timeline-tick" style={{ left: `${left}%` }}>
              <span className={`timeline-tick-label ${edge}`.trim()}>
                {new Date(ts * 1000).toLocaleTimeString(localeTag, {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
            </div>
          );
        })}
      </div>
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
              height: '52%',
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
