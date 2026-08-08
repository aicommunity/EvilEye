import { useEffect } from 'react';
import { streamStop } from '../api';

/** On unmount, notify server that MJPEG consumer left. */
export function useMjpegLifecycle(rid: number | null, sourceId: number | null) {
  useEffect(() => {
    if (rid == null) return;
    return () => {
      void streamStop(rid, sourceId).catch(() => null);
    };
  }, [rid, sourceId]);
}
