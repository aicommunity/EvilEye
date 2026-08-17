import { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';

const SHOW_DELAY_MS = 150;

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

  useEffect(() => {
    if (!want) {
      setShown(false);
      return;
    }
    const timer = window.setTimeout(() => setShown(true), SHOW_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [want]);

  if (!shown) return null;
  const label = seeking ? t('playback.seekingFrame') : t('playback.loadingMetadata');
  const compact = seeking && hasObjects;
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
