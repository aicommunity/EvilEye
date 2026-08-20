import { useMemo, type RefObject } from 'react';
import type { StreamMetadata } from '../../api';
import { MetadataOverlayLayer } from '../overlay/MetadataOverlayLayer';
import { prepareOverlayMetadata } from '../overlay/overlayMath';
import { useVideoLetterbox } from '../overlay/useMediaLetterbox';

export function PlaybackMediaWithOverlay({
  videoRef,
  mediaRef,
  meta,
  showMetadata,
  visible = true,
  density = 'full',
  videoReady = 0,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  mediaRef: RefObject<HTMLElement | null>;
  meta: StreamMetadata | null;
  showMetadata: boolean;
  visible?: boolean;
  density?: 'compact' | 'full';
  videoReady?: number;
}) {
  const layoutBox = useVideoLetterbox(mediaRef, videoRef, [meta, showMetadata, videoReady]);

  const displayMeta = useMemo(() => {
    if (!meta || !showMetadata) return null;
    const video = videoRef.current;
    const w = video?.videoWidth ?? 0;
    const h = video?.videoHeight ?? 0;
    if (w <= 0 || h <= 0) return meta;
    return prepareOverlayMetadata(meta, { w, h });
  }, [meta, showMetadata, videoRef, videoReady]);

  return (
    <MetadataOverlayLayer
      meta={displayMeta}
      layoutBox={layoutBox.width > 0 && layoutBox.height > 0 ? layoutBox : undefined}
      density={density}
      visible={showMetadata && visible}
      renderMode="playback"
    />
  );
}
