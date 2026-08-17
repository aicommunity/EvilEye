import { useLayoutEffect, useState, type RefObject } from 'react';
import { letterboxRect } from '../journals/journalMath';

export function useImageLetterbox(
  containerRef: RefObject<HTMLElement | null>,
  imgRef: RefObject<HTMLImageElement | null>,
  deps: unknown[] = [],
) {
  const [box, setBox] = useState({ left: 0, top: 0, width: 0, height: 0 });

  useLayoutEffect(() => {
    const update = () => {
      const wrap = containerRef.current;
      const img = imgRef.current;
      if (!wrap || !img || !img.naturalWidth) return;
      setBox(letterboxRect(wrap.clientWidth, wrap.clientHeight, img.naturalWidth, img.naturalHeight));
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, deps);

  return box;
}
