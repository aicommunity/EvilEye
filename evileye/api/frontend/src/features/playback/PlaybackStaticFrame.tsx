import { useMemo, useRef, useState } from 'react';
import { journalPreviewUrl, type PlaybackDetectionItem } from '../../api';
import { MetadataOverlayLayer } from '../overlay/MetadataOverlayLayer';
import { useImageLetterbox } from '../overlay/useMediaLetterbox';
import { mergePlaybackMetadata } from './mergePlaybackMetadata';
import { staticFrameToStreamMetadata, type StaticFrameSource } from './markerNavigation';
import { usePlaybackStaticMetadata } from './usePlaybackStaticMetadata';

export function PlaybackStaticFrame({
  frame,
  date,
  showMetadata,
  cameraLabel,
  detectionItems,
  cameraId,
  runId,
  sourceId,
  expanded = false,
}: {
  frame: StaticFrameSource;
  date: string;
  showMetadata: boolean;
  cameraLabel: string;
  detectionItems: PlaybackDetectionItem[];
  cameraId: string;
  runId: number | null;
  sourceId?: number | null;
  expanded?: boolean;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [imgLoaded, setImgLoaded] = useState(0);
  const layoutBox = useImageLetterbox(wrapRef, imgRef, [frame.previewPath, imgLoaded]);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);

  const staticMeta = usePlaybackStaticMetadata({
    camera: cameraId,
    sourceId,
    runId,
    enabled: showMetadata && naturalSize != null,
    frameSize: naturalSize,
  });

  const frameMeta = useMemo(
    () => staticFrameToStreamMetadata(frame, naturalSize, detectionItems),
    [frame, naturalSize, detectionItems],
  );

  const mergedMeta = useMemo(() => {
    if (!showMetadata) return null;
    return mergePlaybackMetadata(staticMeta, frameMeta, { stripObjects: false });
  }, [showMetadata, staticMeta, frameMeta]);

  const previewClass = expanded ? 'expanded-camera-frame' : 'camera-preview';

  return (
    <div ref={wrapRef} className={`playback-static-frame ${previewClass}`} style={{ position: 'relative' }}>
      <img
        ref={imgRef}
        src={journalPreviewUrl({
          path: frame.previewPath,
          date,
          journalType: frame.journalType,
          mode: frame.mode,
        })}
        alt=""
        className={previewClass}
        onLoad={() => {
          const img = imgRef.current;
          if (img?.naturalWidth && img.naturalHeight) {
            setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
          }
          setImgLoaded((n) => n + 1);
        }}
      />
      {showMetadata && mergedMeta ? (
        <MetadataOverlayLayer meta={mergedMeta} layoutBox={layoutBox} density={expanded ? 'full' : 'compact'} />
      ) : null}
      {!showMetadata ? <div className="live-overlay-source">{cameraLabel}</div> : null}
    </div>
  );
}
