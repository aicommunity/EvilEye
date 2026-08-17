import { useEffect, useRef, useState } from 'react';
import { isAbortError, playbackApi, type StreamMetadata } from '../../api';

const STATIC_REFRESH_MS = 60_000;

const staticCache = new Map<string, StreamMetadata | null>();

function staticKey(camera: string, runId: number | null): string {
  return `${camera}:${runId ?? 'none'}`;
}

export function usePlaybackStaticMetadata({
  camera,
  sourceId,
  runId,
  enabled,
}: {
  camera: string;
  sourceId?: number | null;
  runId: number | null;
  enabled: boolean;
}) {
  const [meta, setMeta] = useState<StreamMetadata | null>(null);

  useEffect(() => {
    if (!enabled || !camera) {
      setMeta(null);
      return;
    }

    const key = staticKey(camera, runId);
    const cached = staticCache.get(key);
    if (cached) setMeta(cached);

    let cancelled = false;
    const load = () => {
      void playbackApi
        .metadataStatic(camera, runId, { sourceId: sourceId ?? undefined })
        .then((res) => {
          if (cancelled) return;
          const payload = res.metadata ?? null;
          staticCache.set(key, payload);
          setMeta(payload);
        })
        .catch((e) => {
          if (isAbortError(e) || cancelled) return;
        });
    };

    load();
    const id = window.setInterval(load, STATIC_REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [camera, sourceId, runId, enabled]);

  return meta;
}
