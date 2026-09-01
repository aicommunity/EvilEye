import { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';

const SHOW_DELAY_MS = 4000;
/** Hide "Ищем кадр…" even if video.seeking never clears (503 / hung Range). */
const SEEK_HINT_MAX_MS = 7000;

export function PlaybackBusyHint({
  seeking = false,
  loading = false,
  hasObjects = false,
}: {
  seeking?: boolean;
  loading?: boolean;
  hasObjects?: boolean;
}) {
  const { t } = useI18n();
  const want = seeking || (loading && !hasObjects);
  const [shown, setShown] = useState(false);
  const [seekExpired, setSeekExpired] = useState(false);

  useEffect(() => {
    if (!want) {
      setShown(false);
      setSeekExpired(false);
      return;
    }
    const timer = window.setTimeout(() => setShown(true), SHOW_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [want]);

  useEffect(() => {
    if (!seeking) {
      setSeekExpired(false);
      return;
    }
    const timer = window.setTimeout(() => setSeekExpired(true), SEEK_HINT_MAX_MS);
    return () => window.clearTimeout(timer);
  }, [seeking]);

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
