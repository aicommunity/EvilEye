import { useEffect, useRef, useState } from 'react';
import type { FrameSize, PlaybackCamera, PlaybackSegment } from '../../api';
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
  onExpand,
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
  onExpand: (cameraId: string) => void;
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
          onExpand={() => onExpand(id)}
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
  onExpand,
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
  onExpand: () => void;
}) {
  const mediaRef = useRef<HTMLDivElement>(null);
  const [videoReady, setVideoReady] = useState(0);
  const [frameSize, setFrameSize] = useState<FrameSize | null>(null);
  const { ref, preloadRef, slot, applySync } = usePlaybackCameraSlot(segments, getPosition, positionSec, playing);
  const meta = usePlaybackCameraMetadata({
    cameraId: id,
    camera,
    positionSec,
    runId,
    showMetadata,
    hasVideo: Boolean(slot?.url),
    frameSize,
  });

  const split = Boolean(camera?.split && camera?.src_coords && camera.src_coords.length === 4);

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
        onExpand={onExpand}
        frameSize={frameSize}
        onFrameSize={setFrameSize}
      />
    );
  }

  return (
    <article
      className="camera-card camera-card-mini camera-card-grid playback-cell"
      onDoubleClick={onExpand}
    >
      <div className="camera-card-media" ref={mediaRef} style={{ position: 'relative' }}>
        <PlaybackVideoSurface
          videoRef={ref}
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
        />
      </div>
    </article>
  );
}
