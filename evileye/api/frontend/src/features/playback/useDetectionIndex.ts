import { useEffect, useMemo, useState } from 'react';
import { isAbortError, playbackApi, type PlaybackDetectionItem } from '../../api';
import { mergeGlobalDetectionTs } from './detectionSync';

export function useDetectionIndex({
  cameras,
  date,
  runId,
  fromSec,
  toSec,
  enabled,
}: {
  cameras: string[];
  date: string;
  runId: number | null;
  fromSec: number | null;
  toSec: number | null;
  enabled: boolean;
}) {
  const [byCamera, setByCamera] = useState<Record<string, PlaybackDetectionItem[]>>({});
  const [loading, setLoading] = useState(false);

  const cameraKey = cameras.join(',');

  useEffect(() => {
    if (!enabled || !cameras.length) {
      setByCamera({});
      setLoading(false);
      return;
    }
    const ac = new AbortController();
    setLoading(true);
    void playbackApi
      .detections(cameras, {
        date,
        runId,
        from: fromSec ?? undefined,
        to: toSec ?? undefined,
        signal: ac.signal,
      })
      .then((res) => {
        if (ac.signal.aborted) return;
        const mapped: Record<string, PlaybackDetectionItem[]> = {};
        for (const cam of cameras) {
          mapped[cam] = res.by_camera?.[cam] ?? [];
        }
        setByCamera(mapped);
      })
      .catch((e) => {
        if (isAbortError(e) || ac.signal.aborted) return;
        setByCamera({});
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });
    return () => ac.abort();
  }, [cameraKey, date, runId, fromSec, toSec, enabled]);

  const globalTs = useMemo(() => mergeGlobalDetectionTs(byCamera), [byCamera]);
  const hasDetections = globalTs.length > 0;

  return { byCamera, globalTs, hasDetections, loading };
}
