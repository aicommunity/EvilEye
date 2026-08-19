import { useEffect, useRef, useState } from 'react';
import { isAbortError, playbackApi, type FrameSize, type StreamMetadata } from '../../api';

const STATIC_REFRESH_MS = 60_000;

const staticCache = new Map<string, StreamMetadata | null>();

function staticKey(camera: string, runId: number | null, frameSize: FrameSize): string {
  return `${camera}:${runId ?? 'none'}:${frameSize.w}x${frameSize.h}`;
}

function hasFrameSize(frameSize: FrameSize | null | undefined): frameSize is FrameSize {
  return Boolean(frameSize && frameSize.w > 0 && frameSize.h > 0);
}

export function usePlaybackStaticMetadata({
  camera,
  sourceId,
  runId,
  enabled,
  frameSize,
}: {
  camera: string;
  sourceId?: number | null;
  runId: number | null;
  enabled: boolean;
  frameSize?: FrameSize | null;
}) {
  const [meta, setMeta] = useState<StreamMetadata | null>(null);
  const requestGen = useRef(0);

  useEffect(() => {
    if (!enabled || !camera) {
      setMeta(null);
      return;
    }
    if (!hasFrameSize(frameSize)) {
      // Wait for video dimensions — avoid caching/merging coords normalized for the wrong frame size.
      setMeta(null);
      return;
    }

    const key = staticKey(camera, runId, frameSize);
    const cached = staticCache.get(key);
    if (cached !== undefined) setMeta(cached);

    const gen = ++requestGen.current;
    let cancelled = false;
    const load = () => {
      void playbackApi
        .metadataStatic(camera, runId, {
          sourceId: sourceId ?? undefined,
          frameSize,
        })
        .then((res) => {
          if (cancelled || requestGen.current !== gen) return;
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
  }, [camera, sourceId, runId, enabled, frameSize?.w, frameSize?.h]);

  return meta;
}
