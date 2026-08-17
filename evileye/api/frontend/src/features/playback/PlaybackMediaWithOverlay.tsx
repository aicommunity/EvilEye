import { useMemo, type RefObject } from 'react';
import type { StreamMetadata } from '../../api';
import { MetadataOverlayLayer } from '../overlay/MetadataOverlayLayer';
import { transformMetadataForCrop } from '../overlay/overlayMath';
import { useVideoLetterbox } from '../overlay/useMediaLetterbox';

export function PlaybackMediaWithOverlay({
  videoRef,
  mediaRef,
  meta,
  showMetadata,
  density = 'full',
  srcCoords,
  parentVideoSize,
  videoReady = 0,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  mediaRef: RefObject<HTMLElement | null>;
  meta: StreamMetadata | null;
  showMetadata: boolean;
  density?: 'compact' | 'full';
  srcCoords?: [number, number, number, number] | null;
  parentVideoSize?: { w: number; h: number } | null;
  videoReady?: number;
}) {
  const layoutBox = useVideoLetterbox(mediaRef, videoRef, [meta, showMetadata, videoReady]);

  const displayMeta = useMemo(() => {
    if (!meta || !showMetadata) return null;
    if (!srcCoords?.length || srcCoords.length !== 4) return meta;
    const parentW = parentVideoSize?.w || videoRef.current?.videoWidth || 0;
    const parentH = parentVideoSize?.h || videoRef.current?.videoHeight || 0;
    if (parentW <= 0 || parentH <= 0) return meta;
    return transformMetadataForCrop(meta, srcCoords, parentW, parentH);
  }, [meta, showMetadata, srcCoords, parentVideoSize, videoRef, videoReady]);

  return (
    <MetadataOverlayLayer
      meta={displayMeta}
      layoutBox={layoutBox.width > 0 ? layoutBox : undefined}
      density={density}
      visible={showMetadata}
    />
  );
}
