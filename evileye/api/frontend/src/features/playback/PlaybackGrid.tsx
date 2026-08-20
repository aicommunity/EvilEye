import { useEffect, useRef, useState, type Dispatch, type RefObject, type SetStateAction } from 'react';
import type {
  FrameSize,
  PlaybackCamera,
  PlaybackDetectionItem,
  PlaybackEventInterval,
  PlaybackPlayMode,
  PlaybackSegment,
} from '../../api';
import { useI18n } from '../../i18n';
import {
  PlaybackVideoSurface,
  usePlaybackCameraMetadata,
  usePlaybackCameraSlot,
} from './PlaybackCameraView';
import { SplitPlaybackCell } from './SplitPlaybackCell';

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
  runId,
  showMetadata,
  playMode = 'normal',
  scrubbing = false,
  detectionByCamera = {},
  globalDetectionTs = [],
  eventIntervalsByCamera = {},
  onVideoClock,
  onExpand,
  segmentsLoading = false,
  detectionsReady = true,
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
  runId: number | null;
  showMetadata: boolean;
  playMode?: PlaybackPlayMode;
  scrubbing?: boolean;
  detectionByCamera?: Record<string, PlaybackDetectionItem[]>;
  globalDetectionTs?: number[];
  eventIntervalsByCamera?: Record<string, PlaybackEventInterval[]>;
  onVideoClock?: (globalSec: number) => void;
  onExpand: (cameraId: string) => void;
  segmentsLoading?: boolean;
  detectionsReady?: boolean;
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
          runId={runId}
          showMetadata={showMetadata}
          playMode={playMode}
          scrubbing={scrubbing}
          detectionItems={detectionByCamera[id] ?? []}
          globalDetectionTs={globalDetectionTs}
          eventIntervals={eventIntervalsByCamera[id] ?? []}
          onVideoClock={onVideoClock}
          onExpand={() => onExpand(id)}
          segmentsLoading={segmentsLoading && !(segmentsByCam[id]?.length)}
          detectionsReady={detectionsReady}
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
  runId,
  showMetadata,
  playMode,
  scrubbing,
  detectionItems,
  globalDetectionTs,
  eventIntervals,
  onVideoClock,
  onExpand,
  segmentsLoading = false,
  detectionsReady = true,
}: {
  id: string;
  camera?: PlaybackCamera;
  segments: PlaybackSegment[];
  getPosition: () => number;
  positionSec: number;
  playing: boolean;
  speed: number;
  runId: number | null;
  showMetadata: boolean;
  playMode: PlaybackPlayMode;
  scrubbing: boolean;
  detectionItems: PlaybackDetectionItem[];
  globalDetectionTs: number[];
  eventIntervals: PlaybackEventInterval[];
  onVideoClock?: (globalSec: number) => void;
  onExpand: () => void;
  segmentsLoading?: boolean;
  detectionsReady?: boolean;
}) {
  const mediaRef = useRef<HTMLDivElement>(null);
  const [videoReady, setVideoReady] = useState(0);
  const [frameSize, setFrameSize] = useState<FrameSize | null>(null);
  const { ref, preloadRef, slot, applySync, videoGlobalSec, videoSeeking } = usePlaybackCameraSlot(
    segments,
    getPosition,
    positionSec,
    playing,
    playMode,
    scrubbing,
    onVideoClock,
    id,
  );
  const split = Boolean(camera?.split && camera?.src_coords && camera.src_coords.length === 4);

  useEffect(() => {
    setFrameSize(null);
    setVideoReady(0);
  }, [slot?.url]);

  if (split && slot?.url && camera?.src_coords) {
    return (
      <SplitPlaybackCell
        videoUrl={slot.url}
        srcCoords={camera.src_coords}
        label={id}
        cameraId={id}
        camera={camera}
        sourceId={camera.source_id}
        getPosition={getPosition}
        positionSec={positionSec}
        playing={playing}
        speed={speed}
        startTs={slot.startTs}
        runId={runId}
        showMetadata={showMetadata}
        playMode={playMode}
        scrubbing={scrubbing}
        detectionItems={detectionItems}
        globalDetectionTs={globalDetectionTs}
        eventIntervals={eventIntervals}
        onVideoClock={onVideoClock}
        onExpand={onExpand}
        frameSize={frameSize}
        onFrameSize={setFrameSize}
        detectionsReady={detectionsReady}
      />
    );
  }

  return (
    <NormalPlaybackCell
      id={id}
      camera={camera}
      mediaRef={mediaRef}
      videoRef={ref}
      preloadRef={preloadRef}
      slot={slot}
      applySync={applySync}
      videoReady={videoReady}
      setVideoReady={setVideoReady}
      frameSize={frameSize}
      setFrameSize={setFrameSize}
      positionSec={positionSec}
      playing={playing}
      speed={speed}
      runId={runId}
      showMetadata={showMetadata}
      playMode={playMode}
      scrubbing={scrubbing}
      videoGlobalSec={videoGlobalSec}
      videoSeeking={videoSeeking}
      detectionItems={detectionItems}
      globalDetectionTs={globalDetectionTs}
      eventIntervals={eventIntervals}
      onExpand={onExpand}
      segmentsLoading={segmentsLoading}
      detectionsReady={detectionsReady}
    />
  );
}

function NormalPlaybackCell({
  id,
  camera,
  mediaRef,
  videoRef,
  preloadRef,
  slot,
  applySync,
  videoReady,
  setVideoReady,
  frameSize,
  setFrameSize,
  positionSec,
  playing,
  speed,
  runId,
  showMetadata,
  playMode,
  scrubbing = false,
  videoGlobalSec = null,
  videoSeeking = false,
  detectionItems,
  globalDetectionTs,
  eventIntervals,
  onExpand,
  segmentsLoading = false,
  detectionsReady = true,
}: {
  id: string;
  camera?: PlaybackCamera;
  mediaRef: RefObject<HTMLDivElement>;
  videoRef: RefObject<HTMLVideoElement | null>;
  preloadRef: RefObject<HTMLVideoElement | null>;
  slot: ReturnType<typeof usePlaybackCameraSlot>['slot'];
  applySync: () => void;
  videoReady: number;
  setVideoReady: Dispatch<SetStateAction<number>>;
  frameSize: FrameSize | null;
  setFrameSize: Dispatch<SetStateAction<FrameSize | null>>;
  positionSec: number;
  playing: boolean;
  speed: number;
  runId: number | null;
  showMetadata: boolean;
  playMode: PlaybackPlayMode;
  scrubbing?: boolean;
  videoGlobalSec?: number | null;
  videoSeeking?: boolean;
  detectionItems: PlaybackDetectionItem[];
  globalDetectionTs: number[];
  eventIntervals: PlaybackEventInterval[];
  onExpand: () => void;
  segmentsLoading?: boolean;
  detectionsReady?: boolean;
}) {
  const { meta, loading } = usePlaybackCameraMetadata({
    cameraId: id,
    camera,
    positionSec,
    runId,
    showMetadata,
    hasVideo: Boolean(slot?.url),
    frameSize,
    playing,
    scrubbing,
    videoGlobalSec,
    videoSeeking,
    detectionItems,
    globalDetectionTs,
    eventIntervals,
    detectionsReady,
  });

  return (
    <article
      className="camera-card camera-card-mini camera-card-grid playback-cell"
      onDoubleClick={onExpand}
    >
      <div className="camera-card-media" ref={mediaRef} style={{ position: 'relative' }}>
        <PlaybackVideoSurface
          videoRef={videoRef}
          preloadRef={preloadRef}
          slot={slot}
          mediaRef={mediaRef}
          meta={meta}
          showMetadata={showMetadata}
          videoReady={videoReady}
          setVideoReady={setVideoReady}
          cameraLabel={id}
          onExpand={onExpand}
          onVideoReady={applySync}
          onVideoDimensions={setFrameSize}
          playing={playing}
          speed={speed}
          playMode={playMode}
          loading={loading}
          segmentsLoading={segmentsLoading}
        />
      </div>
    </article>
  );
}
