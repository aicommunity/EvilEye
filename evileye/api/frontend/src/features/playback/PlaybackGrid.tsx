import { useEffect, useRef, useState } from 'react';
import { playbackApi, type PlaybackCamera, type PlaybackSegment } from '../../api';
import { useI18n } from '../../i18n';
import { SplitPlaybackCell } from './SplitPlaybackCell';
import { pickSegmentNear } from './timelineMath';

export type PlaybackMediaSlot = {
  url: string | null;
  startTs: number;
  endTs: number;
};

function nextSegment(segs: PlaybackSegment[], current: PlaybackSegment | null): PlaybackSegment | null {
  if (!current || !segs.length) return null;
  const idx = segs.findIndex((s) => s.path === current.path);
  if (idx < 0 || idx >= segs.length - 1) return null;
  return segs[idx + 1];
}

export function PlaybackGrid({
  cameras,
  cameraDefs,
  cols,
  segmentsByCam,
  getPosition,
  positionSec,
  playing,
  speed,
  mode = 'fixed',
}: {
  cameras: string[];
  cameraDefs: Record<string, PlaybackCamera>;
  cols: number;
  segmentsByCam: Record<string, PlaybackSegment[]>;
  getPosition: () => number;
  positionSec: number;
  playing: boolean;
  speed: number;
  mode?: 'fit' | 'fixed';
}) {
  const { t } = useI18n();
  if (!cameras.length) return <p className="empty">{t('playback.selectCameras')}</p>;
  const fitClass = mode === 'fit' ? ' camera-group-grid--fit' : '';
  return (
    <div
      className={`camera-group-grid${fitClass}`}
      style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
    >
      {cameras.map((id) => (
        <PlaybackCell
          key={id}
          id={id}
          camera={cameraDefs[id]}
          segments={segmentsByCam[id] ?? []}
          getPosition={getPosition}
          positionSec={positionSec}
          playing={playing}
          speed={speed}
        />
      ))}
    </div>
  );
}

function PlaybackCell({
  id,
  camera,
  segments,
  getPosition,
  positionSec,
  playing,
  speed,
}: {
  id: string;
  camera?: PlaybackCamera;
  segments: PlaybackSegment[];
  getPosition: () => number;
  positionSec: number;
  playing: boolean;
  speed: number;
}) {
  const { t } = useI18n();
  const ref = useRef<HTMLVideoElement>(null);
  const preloadRef = useRef<HTMLVideoElement>(null);
  const pathRef = useRef<string | null>(null);
  const slotRef = useRef<PlaybackMediaSlot | null>(null);
  const [slot, setSlot] = useState<PlaybackMediaSlot | null>(null);
  const getPositionRef = useRef(getPosition);
  getPositionRef.current = getPosition;
  const segmentsRef = useRef(segments);
  segmentsRef.current = segments;

  const split = Boolean(camera?.split && camera?.src_coords && camera.src_coords.length === 4);

  const applySync = () => {
    const position = getPositionRef.current();
    const segs = segmentsRef.current;
    const seg = pickSegmentNear(segs, position);
    const nxt = nextSegment(segs, seg);
    const preload = preloadRef.current;

    if (!seg) {
      if (pathRef.current != null) {
        pathRef.current = null;
        slotRef.current = null;
        setSlot(null);
      }
    } else if (seg.path !== pathRef.current) {
      const nextSlot: PlaybackMediaSlot = {
        url: playbackApi.mediaUrl(seg.path),
        startTs: seg.start_ts,
        endTs: seg.end_ts,
      };
      pathRef.current = seg.path;
      slotRef.current = nextSlot;
      setSlot(nextSlot);
    }

    if (preload) {
      if (nxt) {
        const nextUrl = playbackApi.mediaUrl(nxt.path);
        if (preload.getAttribute('src') !== nextUrl) {
          preload.setAttribute('src', nextUrl);
          preload.preload = 'auto';
          try {
            preload.load();
          } catch {
            /* ignore */
          }
        }
      } else if (preload.getAttribute('src')) {
        preload.removeAttribute('src');
      }
    }

    const v = ref.current;
    const current = slotRef.current;
    if (v && current) {
      const local = Math.max(0, position - current.startTs);
      if (Math.abs(v.currentTime - local) > 0.4) {
        try {
          v.currentTime = local;
        } catch {
          /* ignore seek race */
        }
      }
    }
  };

  useEffect(() => {
    let cancelled = false;
    let rafHandle = 0;
    let vfcHandle: number | null = null;

    const schedule = () => {
      if (cancelled) return;
      applySync();
      const el = ref.current as HTMLVideoElement & {
        requestVideoFrameCallback?: (cb: () => void) => number;
        cancelVideoFrameCallback?: (h: number) => void;
      } | null;
      if (playing && el?.requestVideoFrameCallback) {
        vfcHandle = el.requestVideoFrameCallback(() => schedule());
      } else if (playing) {
        rafHandle = window.requestAnimationFrame(() => schedule());
      }
    };

    const onTimeUpdate = () => applySync();
    ref.current?.addEventListener('timeupdate', onTimeUpdate);
    applySync();
    if (playing) schedule();

    return () => {
      cancelled = true;
      ref.current?.removeEventListener('timeupdate', onTimeUpdate);
      if (vfcHandle != null && ref.current && 'cancelVideoFrameCallback' in ref.current) {
        try {
          (ref.current as HTMLVideoElement & { cancelVideoFrameCallback: (h: number) => void }).cancelVideoFrameCallback(vfcHandle);
        } catch {
          /* ignore */
        }
      }
      if (rafHandle) window.cancelAnimationFrame(rafHandle);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- applySync closes over refs
  }, [playing, segments]);

  useEffect(() => {
    applySync();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionSec]);

  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    v.playbackRate = speed;
    if (playing) void v.play().catch(() => null);
    else v.pause();
  }, [playing, speed, slot?.url]);

  if (split && slot?.url && camera?.src_coords) {
    return (
      <SplitPlaybackCell
        videoUrl={slot.url}
        srcCoords={camera.src_coords}
        label={id}
        getPosition={getPosition}
        positionSec={positionSec}
        playing={playing}
        speed={speed}
        startTs={slot.startTs}
      />
    );
  }

  return (
    <article className="camera-card camera-card-grid playback-cell">
      <div className="camera-card-media">
        {slot?.url ? (
          <>
            <video ref={ref} src={slot.url} playsInline className="camera-preview" />
            <video ref={preloadRef} muted playsInline style={{ display: 'none' }} aria-hidden />
          </>
        ) : (
          <div className="camera-preview camera-preview-empty">{t('playback.noSegment')}</div>
        )}
        <div className="camera-card-overlay-top">
          <span className="camera-name">{id}</span>
        </div>
      </div>
    </article>
  );
}
