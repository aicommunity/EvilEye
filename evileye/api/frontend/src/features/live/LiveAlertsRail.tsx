export function LiveAlertsRail({
  eventsTotal,
  objectsTotal,
  cameras,
}: {
  eventsTotal?: number;
  objectsTotal?: number;
  cameras: number;
}) {
  return (
    <div className="metric-grid" style={{ marginBottom: '1rem' }}>
      <div className="metric-card">
        <span className="metric-label">Камеры</span>
        <strong>{cameras}</strong>
      </div>
      <div className="metric-card">
        <span className="metric-label">События</span>
        <strong>{eventsTotal ?? '—'}</strong>
      </div>
      <div className="metric-card">
        <span className="metric-label">Объекты</span>
        <strong>{objectsTotal ?? '—'}</strong>
      </div>
    </div>
  );
}
