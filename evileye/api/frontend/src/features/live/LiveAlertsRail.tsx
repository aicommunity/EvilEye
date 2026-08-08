import { useI18n } from '../../i18n';

export function LiveAlertsRail({
  eventsTotal,
  objectsTotal,
  cameras,
}: {
  eventsTotal?: number;
  objectsTotal?: number;
  cameras: number;
}) {
  const { t } = useI18n();
  return (
    <div className="metric-grid" style={{ marginBottom: '1rem' }}>
      <div className="metric-card">
        <span className="metric-label">{t('live.metrics.cameras')}</span>
        <strong>{cameras}</strong>
      </div>
      <div className="metric-card">
        <span className="metric-label">{t('live.metrics.events')}</span>
        <strong>{eventsTotal ?? '—'}</strong>
      </div>
      <div className="metric-card">
        <span className="metric-label">{t('live.metrics.objects')}</span>
        <strong>{objectsTotal ?? '—'}</strong>
      </div>
    </div>
  );
}
