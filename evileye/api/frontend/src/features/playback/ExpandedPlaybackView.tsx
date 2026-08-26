import { useEffect, useRef, useState } from 'react';
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
  eventIntervals = [],
  onVideoClock,
  onClose,
  detectionsReady = true,
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
  eventIntervals?: PlaybackEventInterval[];
  onVideoClock?: (globalSec: number) => void;
  onClose: () => void;
  detectionsReady?: boolean;
}) {
  const { t } = useI18n();
  const mediaRef = useRef<HTMLDivElement>(null);
  const [videoReady, setVideoReady] = useState(0);
  const [frameSize, setFrameSize] = useState<FrameSize | null>(null);
  const { ref, preloadRef, slot, applySync, videoGlobalSec, videoSeeking, recordingInProgress, mediaEpoch } =
    usePlaybackCameraSlot(
      segments,
      getPosition,
      positionSec,
      playing,
      playMode,
      scrubbing,
      onVideoClock,
      cameraId,
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
    scrubbing,
    videoGlobalSec,
    videoSeeking,
    detectionItems,
    globalDetectionTs,
    eventIntervals,
    detectionsReady,
  });

  useEffect(() => {
    setFrameSize(null);
    setVideoReady(0);
  }, [slot?.url, mediaEpoch]);

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
        <button
          type="button"
          className="icon-btn"
          title={t('live.expandClose')}
          aria-label={t('live.expandClose')}
          onClick={onClose}
        >
          ⤡
        </button>
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
            eventIntervals={eventIntervals}
            onVideoClock={onVideoClock}
            expanded
            frameSize={frameSize}
            onFrameSize={setFrameSize}
            detectionsReady={detectionsReady}
            mediaEpoch={mediaEpoch}
          />
        ) : (
          <PlaybackVideoSurface
            videoRef={ref}
            preloadRef={preloadRef}
            slot={slot}
            mediaEpoch={mediaEpoch}
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
            scrubbing={scrubbing}
            speed={speed}
            playMode={playMode}
            loading={loading}
            recordingInProgress={recordingInProgress}
          />
        )}
      </div>
    </div>
  );
}
