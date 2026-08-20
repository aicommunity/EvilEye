import { useEffect, useRef, useState } from 'react';
import type { PlaybackEventInterval, PlaybackEventMarker, PlaybackSegment } from '../../api';
import { useI18n } from '../../i18n';
import { EventMarkers } from './EventMarkers';
import {
  PAN_CLICK_SLOP_PX,
  buildTimelineDateBoundaries,
  buildTimelineTicks,
  clipRangeToView,
  dayViewSpanSec,
  snapTimelineSeek,
  unixAtClientX,
  zoomViewAt,
} from './timelineMath';

const TIMELINE_HEIGHT_PX = 92;

export function Timeline({
  date,
  viewFrom,
  viewTo,
  position,
  markers,
  segments = [],
  detectionTs = [],
  eventIntervals = [],
  onSeek,
  onViewChange,
  onPanningChange,
}: {
  date: string;
  viewFrom: number | null;
  viewTo: number | null;
  position: number;
  markers: PlaybackEventMarker[];
  segments?: PlaybackSegment[];
  detectionTs?: number[];
  eventIntervals?: PlaybackEventInterval[];
  onSeek: (sec: number) => void;
  onViewChange: (viewFrom: number, viewTo: number) => void;
  onPanningChange?: (panning: boolean) => void;
}) {
  const { t, formatDateTime, formatDate, formatTime } = useI18n();
  const rootRef = useRef<HTMLDivElement>(null);
  const [panning, setPanning] = useState(false);
  const [hoverSec, setHoverSec] = useState<number | null>(null);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startViewFrom: number;
    startViewTo: number;
    moved: boolean;
  } | null>(null);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (viewFrom == null || viewTo == null || viewTo <= viewFrom) return;
      e.preventDefault();
      const maxSpan = dayViewSpanSec(date);
      const span = viewTo - viewFrom;
      const factor = Math.exp(e.deltaY * 0.0015);
      // Hard stop: zoom-out does nothing when already at full day.
      if (factor > 1 && span >= maxSpan - 1) return;
      const rect = el.getBoundingClientRect();
      const anchor = unixAtClientX(e.clientX, rect, viewFrom, viewTo);
      const next = zoomViewAt(viewFrom, viewTo, anchor, factor, { maxSpan });
      if (Math.abs(next.viewFrom - viewFrom) < 1e-6 && Math.abs(next.viewTo - viewTo) < 1e-6) return;
      onViewChange(next.viewFrom, next.viewTo);
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [viewFrom, viewTo, onViewChange, date]);

  if (viewFrom == null || viewTo == null || viewTo <= viewFrom) {
    return (
      <div
        className="playback-timeline"
        style={{
          position: 'relative',
          height: TIMELINE_HEIGHT_PX,
          margin: '0',
          background: 'var(--bg-card-hover)',
          borderRadius: 8,
          border: '1px solid var(--border)',
          overflow: 'hidden',
        }}
      >
        <div className="playback-timeline-empty-banner">{t('playback.timelineEmpty')}</div>
      </div>
    );
  }
  const span = viewTo - viewFrom;
  const pct = ((position - viewFrom) / span) * 100;
  const ticks = buildTimelineTicks(viewFrom, viewTo);
  const dateTicks = buildTimelineDateBoundaries(viewFrom, viewTo);
  const noData = segments.length === 0 && markers.length === 0;

  const seekAtClientX = (clientX: number) => {
    const el = rootRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const raw = unixAtClientX(clientX, rect, viewFrom, viewTo);
    onSeek(snapTimelineSeek(raw, detectionTs, viewFrom, viewTo, rect.width));
  };

  const updateHover = (clientX: number) => {
    const el = rootRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setHoverSec(unixAtClientX(clientX, rect, viewFrom, viewTo));
  };

  return (
    <div
      ref={rootRef}
      className={`playback-timeline playback-timeline-segments${panning ? ' is-panning' : ''}`}
      style={{
        position: 'relative',
        height: TIMELINE_HEIGHT_PX,
        margin: '0',
        background: 'var(--bg-card-hover)',
        borderRadius: 8,
        border: '1px solid var(--border)',
        overflow: 'hidden',
      }}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        const target = e.target as HTMLElement;
        if (target.closest('[data-timeline-marker]')) return;
        dragRef.current = {
          pointerId: e.pointerId,
          startX: e.clientX,
          startViewFrom: viewFrom,
          startViewTo: viewTo,
          moved: false,
        };
      }}
      onPointerMove={(e) => {
        const drag = dragRef.current;
        if (!drag || drag.pointerId !== e.pointerId) {
          if (!drag) updateHover(e.clientX);
          return;
        }
        const el = rootRef.current;
        if (!el) return;
        const dx = e.clientX - drag.startX;
        if (!drag.moved && Math.abs(dx) >= PAN_CLICK_SLOP_PX) {
          drag.moved = true;
          setPanning(true);
          onPanningChange?.(true);
          try {
            (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
          } catch {
            /* ignore */
          }
        }
        if (!drag.moved) {
          updateHover(e.clientX);
          return;
        }
        setHoverSec(null);
        const width = el.getBoundingClientRect().width || 1;
        const dragSpan = drag.startViewTo - drag.startViewFrom;
        const deltaSec = -(dx / width) * dragSpan;
        onViewChange(drag.startViewFrom + deltaSec, drag.startViewTo + deltaSec);
      }}
      onPointerUp={(e) => {
        const drag = dragRef.current;
        if (!drag || drag.pointerId !== e.pointerId) return;
        dragRef.current = null;
        const wasPan = drag.moved;
        setPanning(false);
        if (wasPan) onPanningChange?.(false);
        try {
          (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
        } catch {
          /* ignore */
        }
        if (!wasPan) {
          seekAtClientX(drag.startX);
        }
      }}
      onPointerCancel={() => {
        dragRef.current = null;
        setPanning(false);
        onPanningChange?.(false);
      }}
      onPointerLeave={() => setHoverSec(null)}
    >
      <div className="timeline-date-ticks" aria-hidden>
        {dateTicks.map((ts) => {
          const left = ((ts - viewFrom) / span) * 100;
          const edge =
            left < 3 ? 'timeline-tick-label--start' : left > 97 ? 'timeline-tick-label--end' : '';
          return (
            <div key={`d${ts}`} className="timeline-date-tick" style={{ left: `${left}%` }}>
              <span className={`timeline-date-tick-label ${edge}`.trim()}>
                {formatDate(new Date(ts * 1000))}
              </span>
            </div>
          );
        })}
      </div>
      <div className="timeline-ticks" aria-hidden>
        {ticks.map((ts) => {
          const left = ((ts - viewFrom) / span) * 100;
          const edge =
            left < 3 ? 'timeline-tick-label--start' : left > 97 ? 'timeline-tick-label--end' : '';
          const label = formatTime(new Date(ts * 1000)).slice(0, 5);
          return (
            <div key={ts} className="timeline-tick" style={{ left: `${left}%` }}>
              <span className={`timeline-tick-label ${edge}`.trim()}>{label}</span>
            </div>
          );
        })}
      </div>
      <EventIntervalsCanvas eventIntervals={eventIntervals} viewFrom={viewFrom} viewTo={viewTo} />
      <DetectionTicksCanvas detectionTs={detectionTs} viewFrom={viewFrom} viewTo={viewTo} />
      {segments.map((seg) => {
        const clipped = clipRangeToView(seg.start_ts, seg.end_ts, viewFrom, viewTo);
        if (!clipped) return null;
        return (
          <div
            key={seg.path}
            className="timeline-segment-block"
            style={{
              position: 'absolute',
              left: `${clipped.leftPct}%`,
              width: `${Math.max(0.15, clipped.widthPct)}%`,
              top: '16%',
              height: '48%',
              background: 'rgba(59, 130, 246, 0.45)',
              borderRadius: 4,
              border: '1px solid rgba(59, 130, 246, 0.7)',
              pointerEvents: 'none',
            }}
          />
        );
      })}
      {hoverSec != null && !panning ? (
        <>
          <div
            className="timeline-hover-line"
            style={{ left: `${Math.max(0, Math.min(100, ((hoverSec - viewFrom) / span) * 100))}%` }}
            aria-hidden
          />
          <div
            className="timeline-hover-tooltip"
            style={{ left: `${Math.max(0, Math.min(100, ((hoverSec - viewFrom) / span) * 100))}%` }}
          >
            {formatDateTime(hoverSec)}
          </div>
        </>
      ) : null}
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
      <EventMarkers
        markers={markers}
        from={viewFrom}
        to={viewTo}
        onSelect={(m) => onSeek(m.ts)}
      />
      {noData ? <div className="playback-timeline-empty-banner">{t('playback.timelineNoRecordings')}</div> : null}
    </div>
  );
}

function EventIntervalsCanvas({
  eventIntervals,
  viewFrom,
  viewTo,
}: {
  eventIntervals: PlaybackEventInterval[];
  viewFrom: number;
  viewTo: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const parent = canvas?.parentElement;
    if (!canvas || !parent) return;

    const paint = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = parent.clientWidth;
      const h = parent.clientHeight;
      canvas.width = Math.max(1, Math.round(w * dpr));
      canvas.height = Math.max(1, Math.round(h * dpr));
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const span = viewTo - viewFrom;
      if (!(span > 0) || !eventIntervals.length) return;
      ctx.fillStyle = 'rgba(245, 158, 11, 0.42)';
      for (const it of eventIntervals) {
        if (it.end_ts < viewFrom || it.start_ts > viewTo) continue;
        const leftSec = Math.max(it.start_ts, viewFrom);
        const rightSec = Math.min(it.end_ts, viewTo);
        const left = ((leftSec - viewFrom) / span) * w;
        const width = Math.max(2, ((rightSec - leftSec) / span) * w);
        ctx.fillRect(left, h * 0.06, width, Math.max(4, h * 0.14));
      }
    };

    paint();
    const ro = new ResizeObserver(paint);
    ro.observe(parent);
    return () => ro.disconnect();
  }, [eventIntervals, viewFrom, viewTo]);

  return <canvas ref={canvasRef} className="timeline-event-intervals-canvas" aria-hidden />;
}

export { EventMarkers } from './EventMarkers';
export { buildTimelineTicks } from './timelineMath';

function DetectionTicksCanvas({
  detectionTs,
  viewFrom,
  viewTo,
}: {
  detectionTs: number[];
  viewFrom: number;
  viewTo: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const parent = canvas?.parentElement;
    if (!canvas || !parent) return;

    const paint = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = parent.clientWidth;
      const h = parent.clientHeight;
      canvas.width = Math.max(1, Math.round(w * dpr));
      canvas.height = Math.max(1, Math.round(h * dpr));
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const span = viewTo - viewFrom;
      if (!(span > 0) || !detectionTs.length) return;
      const visibleTs = detectionTs.filter((ts) => ts >= viewFrom && ts <= viewTo);
      if (!visibleTs.length) return;
      ctx.fillStyle = 'rgba(34, 197, 94, 0.95)';
      for (const ts of visibleTs) {
        const x = ((ts - viewFrom) / span) * w;
        ctx.beginPath();
        ctx.arc(x, h * 0.62, 3, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    paint();
    const ro = new ResizeObserver(paint);
    ro.observe(parent);
    return () => ro.disconnect();
  }, [detectionTs, viewFrom, viewTo]);

  return <canvas ref={canvasRef} className="timeline-detection-canvas" aria-hidden />;
}
