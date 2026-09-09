import { useEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n';
import { SEEKING_STUCK_MS } from './playbackVideoSync';

const SHOW_DELAY_MS = 4000;
/** Hide "Ищем кадр…" only when seek has no decode progress for this long. */
const SEEK_HINT_MAX_MS = 7000;
/** Ignore brief seeking false→true flaps so the show-delay does not restart. */
const SEEK_FLAP_MS = 500;

export function PlaybackBusyHint({
  seeking = false,
  loading = false,
  hasObjects = false,
  mediaReadyState = null,
}: {
  seeking?: boolean;
  loading?: boolean;
  hasObjects?: boolean;
  /** HTMLMediaElement.readyState; used to avoid killing long WAN seeks that already decode. */
  mediaReadyState?: number | null;
}) {
  const { t } = useI18n();
  const want = seeking || (loading && !hasObjects);
  const [shown, setShown] = useState(false);
  const [seekExpired, setSeekExpired] = useState(false);
  const wantSinceRef = useRef<number | null>(null);

  useEffect(() => {
    if (!want) {
      const hideTimer = window.setTimeout(() => {
        setShown(false);
        setSeekExpired(false);
        wantSinceRef.current = null;
      }, SEEK_FLAP_MS);
      return () => window.clearTimeout(hideTimer);
    }
    if (wantSinceRef.current == null) wantSinceRef.current = Date.now();
    const elapsed = Date.now() - wantSinceRef.current;
    const remaining = Math.max(0, SHOW_DELAY_MS - elapsed);
    const timer = window.setTimeout(() => setShown(true), remaining);
    return () => window.clearTimeout(timer);
  }, [want]);

  useEffect(() => {
    if (!seeking) {
      setSeekExpired(false);
      return;
    }
    const noProgress = mediaReadyState == null || mediaReadyState < 2;
    // Long WAN seek with decode progress: do not kill the hint by a dumb wall clock.
    if (!noProgress) {
      setSeekExpired(false);
      return;
    }
    const maxMs = Math.max(SEEK_HINT_MAX_MS, SEEKING_STUCK_MS);
    const timer = window.setTimeout(() => setSeekExpired(true), maxMs);
    return () => window.clearTimeout(timer);
  }, [seeking, mediaReadyState]);

  const showSeek = seeking && !seekExpired;
  const showLoad = loading && !hasObjects && !showSeek;
  if (!shown || (!showSeek && !showLoad)) return null;
  const label = showSeek ? t('playback.seekingFrame') : t('playback.loadingMetadata');
  const compact = showSeek && hasObjects;
  return (
    <div
      className={`playback-busy-hint${compact ? ' playback-busy-hint--compact' : ''}`}
      role="status"
      aria-live="polite"
    >
      {label}
    </div>
  );
}
