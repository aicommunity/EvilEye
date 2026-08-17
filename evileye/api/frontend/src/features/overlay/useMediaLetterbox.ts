import { useLayoutEffect, useState, type RefObject } from 'react';
import { letterboxRect } from '../journals/journalMath';

export type MediaNaturalSize = { w: number; h: number };

export function useMediaLetterbox(
  containerRef: RefObject<HTMLElement | null>,
  mediaRef: RefObject<HTMLElement | null>,
  getNaturalSize: () => MediaNaturalSize | null,
  deps: unknown[] = [],
) {
  const [box, setBox] = useState({ left: 0, top: 0, width: 0, height: 0 });

  useLayoutEffect(() => {
    const update = () => {
      const wrap = containerRef.current;
      const media = mediaRef.current;
      if (!wrap || !media) return;
      const size = getNaturalSize();
      if (!size || size.w <= 0 || size.h <= 0) return;
      setBox(letterboxRect(wrap.clientWidth, wrap.clientHeight, size.w, size.h));
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- getNaturalSize is caller-provided
  }, deps);

  return box;
}

/** Letterbox helper for HTMLImageElement previews. */
export function useImageLetterbox(
  containerRef: RefObject<HTMLElement | null>,
  imgRef: RefObject<HTMLImageElement | null>,
  deps: unknown[] = [],
) {
  return useMediaLetterbox(containerRef, imgRef, () => {
    const img = imgRef.current;
    if (!img?.naturalWidth) return null;
    return { w: img.naturalWidth, h: img.naturalHeight };
  }, deps);
}

/** Letterbox helper for HTMLVideoElement playback. */
export function useVideoLetterbox(
  containerRef: RefObject<HTMLElement | null>,
  videoRef: RefObject<HTMLVideoElement | null>,
  deps: unknown[] = [],
) {
  return useMediaLetterbox(containerRef, videoRef, () => {
    const video = videoRef.current;
    if (!video?.videoWidth) return null;
    return { w: video.videoWidth, h: video.videoHeight };
  }, deps);
}
