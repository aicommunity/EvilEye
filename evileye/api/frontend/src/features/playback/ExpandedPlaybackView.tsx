import { useEffect, useRef, useState } from 'react';
import type { PlaybackCamera, PlaybackSegment } from '../../api';
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
  onClose: () => void;
}) {
  const { t } = useI18n();
  const mediaRef = useRef<HTMLDivElement>(null);
  const [videoReady, setVideoReady] = useState(0);
  const { ref, preloadRef, slot } = usePlaybackCameraSlot(segments, getPosition, positionSec, playing);
  const meta = usePlaybackCameraMetadata({
    cameraId,
    camera,
    positionSec,
    runId,
    showMetadata,
    hasVideo: Boolean(slot?.url),
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
        <strong>{cameraId}</strong>
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
            sourceId={camera.source_id}
            getPosition={getPosition}
            positionSec={positionSec}
            playing={playing}
            speed={speed}
            startTs={slot.startTs}
            runId={runId}
            showMetadata={showMetadata}
            expanded
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
            playing={playing}
            speed={speed}
          />
        )}
      </div>
    </div>
  );
}
