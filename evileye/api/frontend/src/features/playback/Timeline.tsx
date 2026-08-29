import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { PlaybackEventInterval, PlaybackEventMarker, PlaybackSegment } from '../../api';
import { useI18n } from '../../i18n';
import { EventMarkers } from './EventMarkers';
import {
  MIN_VIEW_SPAN_SEC,
  PAN_CLICK_SLOP_PX,
  buildTimelineDateLabels,
  buildTimelineTicks,
  clipRangeToView,
  hasAnyPlayableAtPosition,
  intersectPlayableCoverage,
  playableCoverageFraction,
  playableUnionCoverage,
  recordingUnionCoverage,
  dayViewSpanSec,
  panViewWithinDay,
  snapTimelineSeek,
  unixAtClientX,
  zoomViewWithinDay,
} from './timelineMath';

const TIMELINE_HEIGHT_PX = 92;
/** Commit wheel zoom to parent only after the gesture settles. */
const ZOOM_COMMIT_MS = 160;
/** Hide hover tooltip when it would sit on top of the playhead label. */
const HOVER_PLAYHEAD_HIDE_SEC = 2;

type ViewWindow = { viewFrom: number; viewTo: number };

export function Timeline({
  date,
  viewFrom,
  viewTo,
  position,
  markers,
  segments = [],
  segmentsByCamera,
  selectedCameraCount = 0,
  detectionTs = [],
  eventStartTs = [],
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
  segmentsByCamera?: Record<string, PlaybackSegment[]>;
  selectedCameraCount?: number;
  detectionTs?: number[];
  eventStartTs?: number[];
  eventIntervals?: PlaybackEventInterval[];
  onSeek: (sec: number) => void;
  onViewChange: (viewFrom: number, viewTo: number) => void;
  onPanningChange?: (panning: boolean) => void;
}) {
  const { t, formatDateTimeNoYear, formatDate, formatTime } = useI18n();
  const rootRef = useRef<HTMLDivElement>(null);
  const [panning, setPanning] = useState(false);
  const [hoverSec, setHoverSec] = useState<number | null>(null);
  /** Unified local preview for wheel + pan — parent/API only on gesture commit. */
  const [viewPreview, setViewPreview] = useState<ViewWindow | null>(null);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startViewFrom: number;
    startViewTo: number;
    moved: boolean;
  } | null>(null);
  const viewRef = useRef({ viewFrom, viewTo, position, date });
  viewRef.current = { viewFrom, viewTo, position, date };
  const pendingViewRef = useRef<ViewWindow | null>(null);
  const paintRafRef = useRef<number | null>(null);
  const zoomCommitTimerRef = useRef<number | null>(null);
  const onViewChangeRef = useRef(onViewChange);
  onViewChangeRef.current = onViewChange;

  const schedulePaint = (next: ViewWindow) => {
    pendingViewRef.current = next;
    if (paintRafRef.current == null) {
      paintRafRef.current = window.requestAnimationFrame(() => {
        paintRafRef.current = null;
        const pending = pendingViewRef.current;
        if (pending) setViewPreview(pending);
      });
    }
  };

  const commitView = (next: ViewWindow) => {
    const cur = viewRef.current;
    if (
      cur.viewFrom != null &&
      cur.viewTo != null &&
      Math.abs(next.viewFrom - cur.viewFrom) < 1e-6 &&
      Math.abs(next.viewTo - cur.viewTo) < 1e-6
    ) {
      setViewPreview(null);
      pendingViewRef.current = null;
      return;
    }
    onViewChangeRef.current(next.viewFrom, next.viewTo);
  };

  // Drop local preview once the parent view has caught up.
  useLayoutEffect(() => {
    if (!viewPreview || viewFrom == null || viewTo == null) return;
    if (
      Math.abs(viewPreview.viewFrom - viewFrom) < 0.5 &&
      Math.abs(viewPreview.viewTo - viewTo) < 0.5
    ) {
      setViewPreview(null);
      pendingViewRef.current = null;
    }
  }, [viewFrom, viewTo, viewPreview]);

  // Always bind on the stable root (never an empty-state sibling without ref).
  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      const cur = viewRef.current;
      const baseFrom = pendingViewRef.current?.viewFrom ?? cur.viewFrom;
      const baseTo = pendingViewRef.current?.viewTo ?? cur.viewTo;
      if (baseFrom == null || baseTo == null || baseTo <= baseFrom) return;
      e.preventDefault();
      e.stopPropagation();
      const maxSpan = dayViewSpanSec(cur.date);
      const span = baseTo - baseFrom;
      let dy = e.deltaY;
      if (e.deltaMode === 1) dy *= 16;
      if (e.deltaMode === 2) dy *= TIMELINE_HEIGHT_PX;
      // Ignore tiny trackpad noise.
      if (Math.abs(dy) < 0.5) return;
      const factor = Math.exp(dy * 0.0024);
      if (factor > 1 && span >= maxSpan - 1) return;
      if (factor < 1 && span <= MIN_VIEW_SPAN_SEC + 1) return;
      const rect = el.getBoundingClientRect();
      const playheadInView = cur.position >= baseFrom && cur.position <= baseTo;
      const anchor = playheadInView ? cur.position : unixAtClientX(e.clientX, rect, baseFrom, baseTo);
      const next = zoomViewWithinDay(baseFrom, baseTo, anchor, factor, cur.date);
      if (Math.abs(next.viewFrom - baseFrom) < 1e-6 && Math.abs(next.viewTo - baseTo) < 1e-6) return;
      schedulePaint(next);
      if (zoomCommitTimerRef.current != null) window.clearTimeout(zoomCommitTimerRef.current);
      zoomCommitTimerRef.current = window.setTimeout(() => {
        zoomCommitTimerRef.current = null;
        const pending = pendingViewRef.current;
        if (pending) commitView(pending);
      }, ZOOM_COMMIT_MS);
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      el.removeEventListener('wheel', onWheel);
      if (paintRafRef.current != null) {
        window.cancelAnimationFrame(paintRafRef.current);
        paintRafRef.current = null;
      }
      if (zoomCommitTimerRef.current != null) {
        window.clearTimeout(zoomCommitTimerRef.current);
        zoomCommitTimerRef.current = null;
      }
    };
  }, [date]);

  const hasView = viewFrom != null && viewTo != null && viewTo > viewFrom;
  const displayFrom = hasView ? (viewPreview?.viewFrom ?? viewFrom!) : 0;
  const displayTo = hasView ? (viewPreview?.viewTo ?? viewTo!) : 1;
  const interacting = hasView && (viewPreview != null || panning);
  const span = displayTo - displayFrom;
  const pct = hasView ? ((position - displayFrom) / span) * 100 : 0;
  const ticks = hasView ? buildTimelineTicks(displayFrom, displayTo) : [];
  const dateTicks = hasView ? buildTimelineDateLabels(displayFrom, displayTo) : [];
  const noData =
    segments.length === 0 && markers.length === 0 && detectionTs.length === 0 && eventIntervals.length === 0;
  const playheadInView = hasView && position >= displayFrom && position <= displayTo;
  const playheadInGap =
    hasView && segmentsByCamera && !hasAnyPlayableAtPosition(segmentsByCamera, position);
  const showHoverTooltip =
    hoverSec != null &&
    !panning &&
    !(playheadInView && Math.abs(hoverSec - position) < HOVER_PLAYHEAD_HIDE_SEC);

  const seekAtClientX = (clientX: number) => {
    if (!hasView) return;
    const el = rootRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const raw = unixAtClientX(clientX, rect, displayFrom, displayTo);
    onSeek(snapTimelineSeek(raw, detectionTs, displayFrom, displayTo, rect.width, segmentsByCamera, eventStartTs));
  };

  const updateHover = (clientX: number) => {
    if (!hasView) return;
    const el = rootRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setHoverSec(unixAtClientX(clientX, rect, displayFrom, displayTo));
  };

  const endPan = (wasPan: boolean) => {
    setPanning(false);
    if (wasPan) onPanningChange?.(false);
    if (wasPan) {
      const pending = pendingViewRef.current;
      if (pending) commitView(pending);
    }
  };

  const fullCoverage =
    hasView && segmentsByCamera && selectedCameraCount > 1
      ? intersectPlayableCoverage(segmentsByCamera, displayFrom, displayTo)
      : [];
  const playableUnion =
    hasView && segmentsByCamera ? playableUnionCoverage(segmentsByCamera, displayFrom, displayTo) : [];
  const recordingUnion =
    hasView && segmentsByCamera ? recordingUnionCoverage(segmentsByCamera, displayFrom, displayTo) : [];

  // One stable root for the Timeline lifetime so the wheel listener survives
  // empty → loaded transitions (swapping roots left the listener on a detached node).
  return (
    <div
      ref={rootRef}
      className={
        hasView
          ? `playback-timeline playback-timeline-segments${panning ? ' is-panning' : ''}${interacting ? ' is-interacting' : ''}`
          : 'playback-timeline'
      }
      style={{
        position: 'relative',
        height: TIMELINE_HEIGHT_PX,
        margin: '0',
        background: 'var(--bg-card-hover)',
        borderRadius: 8,
        border: '1px solid var(--border)',
        overflow: 'hidden',
      }}
      onPointerDown={
        hasView
          ? (e) => {
              if (e.button !== 0) return;
              const target = e.target as HTMLElement;
              if (target.closest('[data-timeline-marker]')) return;
              // Cancel pending wheel commit so pan owns the gesture.
              if (zoomCommitTimerRef.current != null) {
                window.clearTimeout(zoomCommitTimerRef.current);
                zoomCommitTimerRef.current = null;
              }
              dragRef.current = {
                pointerId: e.pointerId,
                startX: e.clientX,
                startViewFrom: displayFrom,
                startViewTo: displayTo,
                moved: false,
              };
            }
          : undefined
      }
      onPointerMove={
        hasView
          ? (e) => {
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
              const next = panViewWithinDay(
                drag.startViewFrom,
                drag.startViewTo,
                deltaSec,
                viewRef.current.date,
              );
              schedulePaint(next);
            }
          : undefined
      }
      onPointerUp={
        hasView
          ? (e) => {
              const drag = dragRef.current;
              if (!drag || drag.pointerId !== e.pointerId) return;
              dragRef.current = null;
              const wasPan = drag.moved;
              try {
                (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
              } catch {
                /* ignore */
              }
              if (!wasPan) {
                seekAtClientX(e.clientX);
              }
              endPan(wasPan);
            }
          : undefined
      }
      onPointerCancel={
        hasView
          ? () => {
              const drag = dragRef.current;
              const wasPan = Boolean(drag?.moved);
              dragRef.current = null;
              endPan(wasPan);
            }
          : undefined
      }
      onPointerLeave={hasView ? () => setHoverSec(null) : undefined}
    >
      {!hasView ? (
        <div className="playback-timeline-empty-banner">{t('playback.timelineEmpty')}</div>
      ) : (
        <>
          <div className="timeline-date-ticks" aria-hidden>
            {dateTicks.map((ts) => {
              const left = ((ts - displayFrom) / span) * 100;
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
              const left = ((ts - displayFrom) / span) * 100;
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
          {!interacting ? (
            <>
              <EventIntervalsCanvas eventIntervals={eventIntervals} viewFrom={displayFrom} viewTo={displayTo} />
              <DetectionTicksCanvas detectionTs={detectionTs} viewFrom={displayFrom} viewTo={displayTo} />
            </>
          ) : null}
          {recordingUnion.map((interval, idx) => {
            const clipped = clipRangeToView(interval.from, interval.to, displayFrom, displayTo);
            if (!clipped) return null;
            return (
              <div
                key={`rec-${interval.from}-${idx}`}
                className="timeline-segment-block timeline-segment-block--recording"
                style={{
                  position: 'absolute',
                  left: `${clipped.leftPct}%`,
                  width: `${Math.max(0.15, clipped.widthPct)}%`,
                  top: '16%',
                  height: '48%',
                  background:
                    'repeating-linear-gradient(135deg, rgba(148, 163, 184, 0.35) 0 6px, rgba(100, 116, 139, 0.2) 6px 12px)',
                  borderRadius: 4,
                  border: '1px dashed rgba(148, 163, 184, 0.75)',
                  pointerEvents: 'none',
                }}
              />
            );
          })}
          {playableUnion.map((interval, idx) => {
            const clipped = clipRangeToView(interval.from, interval.to, displayFrom, displayTo);
            if (!clipped) return null;
            const mid = (Math.max(interval.from, displayFrom) + Math.min(interval.to, displayTo)) / 2;
            const coverage =
              segmentsByCamera && selectedCameraCount > 0
                ? playableCoverageFraction(segmentsByCamera, mid, selectedCameraCount)
                : 1;
            const opacity = 0.35 + 0.65 * coverage;
            return (
              <div
                key={`play-${interval.from}-${idx}`}
                className="timeline-segment-block"
                style={{
                  position: 'absolute',
                  left: `${clipped.leftPct}%`,
                  width: `${Math.max(0.15, clipped.widthPct)}%`,
                  top: '16%',
                  height: '48%',
                  background: `rgba(59, 130, 246, ${0.45 * opacity})`,
                  borderRadius: 4,
                  border: `1px solid rgba(59, 130, 246, ${0.7 * opacity})`,
                  pointerEvents: 'none',
                }}
              />
            );
          })}
          {fullCoverage.map((interval, idx) => {
            const clipped = clipRangeToView(interval.from, interval.to, displayFrom, displayTo);
            if (!clipped) return null;
            return (
              <div
                key={`full-${interval.from}-${idx}`}
                className="timeline-segment-block timeline-segment-block--full"
                style={{
                  position: 'absolute',
                  left: `${clipped.leftPct}%`,
                  width: `${Math.max(0.15, clipped.widthPct)}%`,
                  top: '62%',
                  height: '8%',
                  background: 'rgba(59, 130, 246, 0.85)',
                  borderRadius: 2,
                  pointerEvents: 'none',
                }}
              />
            );
          })}
          {showHoverTooltip && hoverSec != null ? (
            <>
              <div
                className="timeline-hover-line"
                style={{ left: `${Math.max(0, Math.min(100, ((hoverSec - displayFrom) / span) * 100))}%` }}
                aria-hidden
              />
              <div
                className="timeline-hover-tooltip"
                style={{ left: `${Math.max(0, Math.min(100, ((hoverSec - displayFrom) / span) * 100))}%` }}
              >
                {formatDateTimeNoYear(hoverSec)}
              </div>
            </>
          ) : hoverSec != null && !panning ? (
            <div
              className="timeline-hover-line"
              style={{ left: `${Math.max(0, Math.min(100, ((hoverSec - displayFrom) / span) * 100))}%` }}
              aria-hidden
            />
          ) : null}
          <div
            className={`timeline-playhead${playheadInGap ? ' timeline-playhead--gap' : ''}`}
            style={{
              position: 'absolute',
              left: `${Math.max(0, Math.min(100, pct))}%`,
              top: 0,
              bottom: 0,
              width: 2,
              background: playheadInGap ? 'rgba(239, 68, 68, 0.85)' : 'var(--accent)',
              pointerEvents: 'none',
            }}
          />
          {playheadInView ? (
            <div
              className="timeline-playhead-tooltip"
              style={{ left: `${Math.max(0, Math.min(100, pct))}%` }}
            >
              {formatDateTimeNoYear(position)}
            </div>
          ) : null}
          {!interacting ? (
            <EventMarkers markers={markers} from={displayFrom} to={displayTo} onSelect={(m) => onSeek(m.ts)} />
          ) : null}
          {noData ? <div className="playback-timeline-empty-banner">{t('playback.timelineNoRecordings')}</div> : null}
        </>
      )}
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
