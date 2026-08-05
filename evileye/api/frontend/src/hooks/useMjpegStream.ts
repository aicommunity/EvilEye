import { useCallback, useEffect, useRef, useState } from 'react';
import { streamMjpgUrl, streamStatus } from '../api';
import { useMjpegLifecycle } from './useMjpegLifecycle';

export type MjpegPhase = 'idle' | 'warming' | 'ready' | 'streaming' | 'error';

const WARM_MS = 5000;
const POLL_MS = 450;
const KEEPALIVE_MS = 12000;
const ERROR_BACKOFF_MS = [1000, 2000, 4000, 8000];
const MAX_IMG_ERRORS = 4;

export function shouldAttachMjpeg(
  status: { has_frame?: boolean; web_stream_available?: boolean } | null,
  elapsedMs: number,
  warmMs: number = WARM_MS,
): boolean {
  if (status && (status.has_frame || status.web_stream_available)) return true;
  return elapsedMs >= warmMs;
}

export function useMjpegStream(opts: {
  rid: number | null;
  sourceId: number | null;
  fps?: number;
  enabled: boolean;
}): {
  phase: MjpegPhase;
  src: string;
  error: string | null;
  retry: () => void;
  onImgError: () => void;
  onImgLoad: () => void;
  attempt: number;
} {
  const { rid, sourceId, fps = 8, enabled } = opts;
  const [phase, setPhase] = useState<MjpegPhase>('idle');
  const [src, setSrc] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [generation, setGeneration] = useState(0);
  const imgErrorCount = useRef(0);
  const retryTimer = useRef<number | null>(null);

  useMjpegLifecycle(enabled && rid != null ? rid : null, sourceId);

  const clearRetryTimer = () => {
    if (retryTimer.current != null) {
      window.clearTimeout(retryTimer.current);
      retryTimer.current = null;
    }
  };

  const buildSrc = useCallback(
    (bust: number) => {
      if (rid == null) return '';
      const base = streamMjpgUrl(rid, fps, sourceId);
      const sep = base.includes('?') ? '&' : '?';
      return `${base}${sep}t=${bust}`;
    },
    [rid, fps, sourceId],
  );

  const retry = useCallback(() => {
    clearRetryTimer();
    imgErrorCount.current = 0;
    setError(null);
    setSrc('');
    setPhase(enabled && rid != null ? 'warming' : 'idle');
    setAttempt((a) => a + 1);
    setGeneration((g) => g + 1);
  }, [enabled, rid]);

  const onImgLoad = useCallback(() => {
    imgErrorCount.current = 0;
    setPhase('streaming');
    setError(null);
  }, []);

  const onImgError = useCallback(() => {
    imgErrorCount.current += 1;
    if (imgErrorCount.current > MAX_IMG_ERRORS) {
      setPhase('error');
      setError('streamError');
      setSrc('');
      return;
    }
    const delay = ERROR_BACKOFF_MS[Math.min(imgErrorCount.current - 1, ERROR_BACKOFF_MS.length - 1)];
    setPhase('warming');
    setSrc('');
    clearRetryTimer();
    retryTimer.current = window.setTimeout(() => {
      setAttempt((a) => a + 1);
      setGeneration((g) => g + 1);
    }, delay);
  }, []);

  useEffect(() => {
    if (!enabled || rid == null) {
      setPhase('idle');
      setSrc('');
      setError(null);
      return;
    }

    let cancelled = false;
    let attached = false;
    let pollId = 0;
    const startedAt = Date.now();
    setPhase('warming');
    setSrc('');
    setError(null);

    const attach = (bust: number) => {
      if (cancelled || attached) return;
      attached = true;
      if (pollId) window.clearInterval(pollId);
      setSrc(buildSrc(bust));
      setPhase('ready');
    };

    const warmOnce = async () => {
      try {
        const st = await streamStatus(rid, sourceId, 'stream');
        if (cancelled) return;
        const elapsed = Date.now() - startedAt;
        if (shouldAttachMjpeg(st, elapsed)) {
          attach(Date.now());
        }
      } catch {
        if (cancelled) return;
        const elapsed = Date.now() - startedAt;
        if (elapsed >= WARM_MS) {
          attach(Date.now());
        }
      }
    };

    void warmOnce();

    pollId = window.setInterval(() => {
      if (cancelled || attached) return;
      void (async () => {
        const elapsed = Date.now() - startedAt;
        try {
          const st = await streamStatus(rid, sourceId, 'stream');
          if (cancelled || attached) return;
          if (shouldAttachMjpeg(st, elapsed)) {
            attach(Date.now());
          }
        } catch {
          if (cancelled || attached) return;
          if (elapsed >= WARM_MS) {
            attach(Date.now());
          }
        }
      })();
    }, POLL_MS);

    const keepId = window.setInterval(() => {
      if (cancelled || (typeof document !== 'undefined' && document.hidden)) return;
      void streamStatus(rid, sourceId, 'stream').catch(() => undefined);
    }, KEEPALIVE_MS);

    return () => {
      cancelled = true;
      window.clearInterval(pollId);
      window.clearInterval(keepId);
      clearRetryTimer();
    };
  }, [enabled, rid, sourceId, fps, generation, buildSrc]);

  return { phase, src, error, retry, onImgError, onImgLoad, attempt };
}
