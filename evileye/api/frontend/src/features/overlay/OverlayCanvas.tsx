import type { CSSProperties } from 'react';
import type { StreamMetadata, StreamMetadataObject } from '../../api';
import { formatObjectLabel, polygonCentroid, rgbArrayToCss } from './overlayMath';

export type OverlayLayoutBox = {
  left: number;
  top: number;
  width: number;
  height: number;
};

export type OverlayDensity = 'compact' | 'full';
export type OverlayRenderMode = 'live' | 'playback';

export function OverlayCanvas({
  meta,
  layoutBox,
  density = 'full',
  renderMode = 'live',
}: {
  meta: StreamMetadata | null;
  layoutBox?: OverlayLayoutBox;
  density?: OverlayDensity;
  renderMode?: OverlayRenderMode;
}) {
  const payload = meta;
  const hasContent = Boolean(
    payload?.objects?.length ||
    payload?.zones?.length ||
    payload?.debug_rois?.length ||
    payload?.signalization ||
    payload?.event_labels?.length ||
    payload?.overlay?.source_name ||
    payload?.overlay?.time_label,
  );
  if (!hasContent || !payload) return null;

  const style: CSSProperties = layoutBox
    ? {
        position: 'absolute',
        left: layoutBox.left,
        top: layoutBox.top,
        width: layoutBox.width || '100%',
        height: layoutBox.height || '100%',
        pointerEvents: 'none',
      }
    : {
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
      };

  const isPlayback = renderMode === 'playback';
  const highlightedZone = payload.highlight_zone_name ? String(payload.highlight_zone_name) : null;
  return (
    <div style={style} className="live-overlay-root">
      <svg className="journal-preview-overlay" viewBox="0 0 100 100" preserveAspectRatio="none">
        {density === 'full'
          ? (payload.debug_rois ?? []).map((roi, i) => {
              const [x1, y1, x2, y2] = roi;
              return (
                <rect
                  key={`d${i}`}
                  x={x1 * 100}
                  y={y1 * 100}
                  width={(x2 - x1) * 100}
                  height={(y2 - y1) * 100}
                  fill="none"
                  stroke="#3b82f6"
                  strokeWidth="1.5"
                  vectorEffect="non-scaling-stroke"
                />
              );
            })
          : null}
        {(payload.zones ?? []).map((z, i) => {
          if (!z.points?.length) return null;
          const zoneHighlighted = highlightedZone && z.name && String(z.name) === highlightedZone;
          const points = z.points.map(([x, y]) => `${x * 100},${y * 100}`).join(' ');
          return (
            <g key={`z${i}`}>
              <polygon
                points={points}
                fill={zoneHighlighted ? 'rgba(245, 158, 11, 0.35)' : 'rgba(239,68,68,0.15)'}
                stroke={zoneHighlighted ? '#f59e0b' : '#ef4444'}
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
              />
              {density === 'full' && z.name ? (
                <text
                  x={polygonCentroid(z.points)[0] * 100}
                  y={polygonCentroid(z.points)[1] * 100}
                  fill="#ef4444"
                  fontSize="3.4"
                  textAnchor="middle"
                >
                  {z.name}
                </text>
              ) : null}
            </g>
          );
        })}
        {!isPlayback && density === 'full'
          ? (payload.objects ?? []).map((o, i) => {
              if (!o.trail?.length || o.trail.length < 2) return null;
              const points = o.trail.map(([x, y]) => `${x * 100},${y * 100}`).join(' ');
              return (
                <polyline
                  key={`t${i}`}
                  points={points}
                  fill="none"
                  stroke="#ef4444"
                  strokeWidth="1.2"
                  vectorEffect="non-scaling-stroke"
                />
              );
            })
          : null}
        {!isPlayback ? (payload.objects ?? []).map((o, i) => {
          const b = o.bbox;
          if (!b || b.length !== 4) return null;
          const [x1, y1, x2, y2] = b;
          return (
            <rect
              key={`o${i}`}
              x={x1 * 100}
              y={y1 * 100}
              width={(x2 - x1) * 100}
              height={(y2 - y1) * 100}
              fill="none"
              stroke={o.event_active ? '#ef4444' : '#22c55e'}
              strokeWidth={density === 'compact' ? '2.5' : '1.5'}
              vectorEffect="non-scaling-stroke"
            />
          );
        }) : null}
      </svg>
      {!isPlayback && density === 'full' ? (
        <div className="live-overlay-label-layer">
          {(payload.objects ?? []).map((o, i) => renderObjectLabel(o, i))}
          {(payload.objects ?? []).map((o, i) => renderObjectAttributes(o, i))}
        </div>
      ) : !isPlayback ? (
        <div className="live-overlay-label-layer live-overlay-label-layer--compact">
          {(payload.objects ?? []).map((o, i) => renderCompactObjectLabel(o, i))}
        </div>
      ) : null}
      {payload.signalization && (payload.event_labels?.length ?? 0) > 0 ? (
        <div
          className="live-event-banner"
          style={{
            borderColor: rgbArrayToCss(payload.event_color),
            color: rgbArrayToCss(payload.event_color),
          }}
        >
          {(payload.event_labels ?? []).map((label, idx) => (
            <div key={`e${idx}`}>{label}</div>
          ))}
        </div>
      ) : null}
      {payload.overlay?.source_name ? <div className="live-overlay-source">{payload.overlay.source_name}</div> : null}
      {payload.overlay?.time_label ? <div className="live-overlay-time">{payload.overlay.time_label}</div> : null}
    </div>
  );
}

function renderCompactObjectLabel(o: StreamMetadataObject, i: number) {
  const b = o.bbox;
  if (!b || b.length !== 4) return null;
  const [x1, y1] = b;
  const classLabel = o.class_name ?? (o.class_id != null ? `class_${o.class_id}` : 'object');
  const trackLabel = o.track_id != null ? String(o.track_id) : '?';
  return (
    <div
      key={`lc${i}`}
      className="live-overlay-label live-overlay-label--compact"
      style={{
        left: `${x1 * 100}%`,
        top: `${y1 * 100}%`,
      }}
    >
      {classLabel} [{trackLabel}]
    </div>
  );
}

function renderObjectLabel(o: StreamMetadataObject, i: number) {
  const b = o.bbox;
  if (!b || b.length !== 4) return null;
  const [x1, y1] = b;
  return (
    <div
      key={`l${i}`}
      className="live-overlay-label"
      style={{
        left: `${x1 * 100}%`,
        top: `${y1 * 100}%`,
      }}
    >
      {formatObjectLabel(o)}
    </div>
  );
}

function renderObjectAttributes(o: StreamMetadataObject, i: number) {
  const b = o.bbox;
  if (!b || b.length !== 4 || !o.attributes?.length) return null;
  const [x1, , , y2] = b;
  return (
    <div
      key={`a${i}`}
      className="live-overlay-attrs"
      style={{
        left: `${x1 * 100}%`,
        top: `${y2 * 100}%`,
      }}
    >
      {o.attributes.slice(0, 4).map((attr, idx) => (
        <div key={`${attr.name}-${idx}`} className={`live-overlay-attr live-overlay-attr--${attr.state || 'none'}`}>
          {attr.name}: {attr.state} ({Number(attr.confidence ?? 0).toFixed(2)})
        </div>
      ))}
    </div>
  );
}
