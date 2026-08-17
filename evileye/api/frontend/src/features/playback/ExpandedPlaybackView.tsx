import { useEffect, useRef, useState } from 'react';
import type {
  FrameSize,
  PlaybackCamera,
  PlaybackDetectionItem,
  PlaybackPlayMode,
  PlaybackSegment,
} from '../../api';
import { Button } from '../../components/ui';
import { useI18n } from '../../i18n';
import {
  PlaybackVideoSurface,
  usePlaybackCameraMetadata,
  usePlaybackCameraSlot,
} from './PlaybackCameraView';
import { SplitPlaybackCell } from './SplitPlaybackCell';

export function ExpandedPlaybackView({
  cameraId,
  camera,
  segments,
  getPosition,
  positionSec,
  playing,
  speed,
  runId,
  showMetadata,
  playMode = 'normal',
  scrubbing = false,
  detectionItems = [],
  globalDetectionTs = [],
  onVideoClock,
  onClose,
}: {
  cameraId: string;
  camera?: PlaybackCamera;
  segments: PlaybackSegment[];
  getPosition: () => number;
  positionSec: number;
  playing: boolean;
  speed: number;
  runId: number | null;
  showMetadata: boolean;
  playMode?: PlaybackPlayMode;
  scrubbing?: boolean;
  detectionItems?: PlaybackDetectionItem[];
  globalDetectionTs?: number[];
  onVideoClock?: (globalSec: number) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const mediaRef = useRef<HTMLDivElement>(null);
  const [videoReady, setVideoReady] = useState(0);
  const [frameSize, setFrameSize] = useState<FrameSize | null>(null);
  const { ref, preloadRef, slot, applySync } = usePlaybackCameraSlot(
    segments,
    getPosition,
    positionSec,
    playing,
    playMode,
    scrubbing,
    onVideoClock,
  );
  const { meta, loading } = usePlaybackCameraMetadata({
    cameraId,
    camera,
    positionSec,
    runId,
    showMetadata,
    hasVideo: Boolean(slot?.url),
    frameSize,
    playing,
    detectionItems,
    globalDetectionTs,
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const split = Boolean(camera?.split && camera?.src_coords && camera.src_coords.length === 4);

  return (
    <div className="expanded-camera-view">
      <div className="expanded-camera-toolbar">
        <strong>{camera?.name ?? cameraId}</strong>
        <span className="hint">
          {t('playback.expandCameraHint', {
            id: cameraId,
            sid: camera?.source_id ?? '—',
            run: runId ?? '—',
          })}
        </span>
        <Button size="sm" variant="outline" onClick={onClose}>
          {t('live.expandClose')}
        </Button>
      </div>
      <div className="expanded-camera-media" ref={mediaRef} style={{ position: 'relative' }}>
        {split && slot?.url && camera?.src_coords ? (
          <SplitPlaybackCell
            videoUrl={slot.url}
            srcCoords={camera.src_coords}
            label={cameraId}
            cameraId={cameraId}
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
            onVideoClock={onVideoClock}
            expanded
            frameSize={frameSize}
            onFrameSize={setFrameSize}
          />
        ) : (
          <PlaybackVideoSurface
            videoRef={ref}
            preloadRef={preloadRef}
            slot={slot}
            mediaRef={mediaRef}
            meta={meta}
            showMetadata={showMetadata}
            videoReady={videoReady}
            setVideoReady={setVideoReady}
            cameraLabel={cameraId}
            expanded
            onVideoReady={applySync}
            onVideoDimensions={setFrameSize}
            playing={playing}
            speed={speed}
            playMode={playMode}
            loading={loading}
          />
        )}
      </div>
    </div>
  );
}
