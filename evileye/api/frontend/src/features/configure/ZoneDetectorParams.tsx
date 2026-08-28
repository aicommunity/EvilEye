import { useEffect, useState } from 'react';
import { configGetSection, configPutSection } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';
import { formatInt, INT_STEP, parseIntInput } from './numberFormat';

type EventsDetectorsSection = {
  ZoneEventsDetector?: {
    event_threshold?: number;
    zone_left_threshold?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
};

export function ZoneDetectorParams({
  configName,
  readOnly,
  onSaved,
}: {
  configName: string;
  readOnly: boolean;
  onSaved?: (restartRequired: boolean) => void;
}) {
  const { t } = useI18n();
  const { showError, showSuccess } = useToast();
  const [eventThreshold, setEventThreshold] = useState(2);
  const [zoneLeftThreshold, setZoneLeftThreshold] = useState(3);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void configGetSection(configName, 'events_detectors')
      .then((data) => {
        if (cancelled) return;
        const section = (data ?? {}) as EventsDetectorsSection;
        const zone = section.ZoneEventsDetector ?? {};
        setEventThreshold(typeof zone.event_threshold === 'number' ? zone.event_threshold : 2);
        setZoneLeftThreshold(typeof zone.zone_left_threshold === 'number' ? zone.zone_left_threshold : 3);
      })
      .catch((e) => showError(e instanceof Error ? e.message : String(e)))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [configName, showError]);

  const save = () => {
    void configGetSection(configName, 'events_detectors')
      .then((data) => {
        const section = { ...((data ?? {}) as EventsDetectorsSection) };
        const zone = { ...(section.ZoneEventsDetector ?? {}) };
        zone.event_threshold = eventThreshold;
        zone.zone_left_threshold = zoneLeftThreshold;
        section.ZoneEventsDetector = zone;
        return configPutSection(configName, 'events_detectors', section);
      })
      .then(() => {
        showSuccess(t('configure.editors.detectorParamsSaved'));
        onSaved?.(true);
      })
      .catch((e) => showError(e instanceof Error ? e.message : String(e)));
  };

  if (loading) return <p className="hint">{t('common.loading')}</p>;

  return (
    <div className="zone-detector-params" style={{ marginTop: 12 }}>
      <h4 style={{ margin: '0 0 8px' }}>{t('configure.editors.detectorParamsTitle')}</h4>
      <p className="hint">{t('configure.editors.detectorParamsHint')}</p>
      <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8 }}>
        <label>
          {t('configure.editors.eventThreshold')}{' '}
          <input
            type="number"
            step={INT_STEP}
            min={0}
            disabled={readOnly}
            value={formatInt(eventThreshold)}
            onChange={(e) => setEventThreshold(parseIntInput(e.target.value) ?? 0)}
          />
        </label>
        <label>
          {t('configure.editors.zoneLeftThreshold')}{' '}
          <input
            type="number"
            step={INT_STEP}
            min={0}
            disabled={readOnly}
            value={formatInt(zoneLeftThreshold)}
            onChange={(e) => setZoneLeftThreshold(parseIntInput(e.target.value) ?? 0)}
          />
        </label>
        {!readOnly ? (
          <Button size="sm" variant="outline" onClick={() => void save()}>
            {t('configure.editors.saveDetectorParams')}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
