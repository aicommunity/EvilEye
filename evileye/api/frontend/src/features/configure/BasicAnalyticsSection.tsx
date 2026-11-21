import { useI18n } from '../../i18n';
import { FormField, FormGrid } from './formLayout';

export function BasicAnalyticsSection({
  analyticsEnabled,
  recordingSummary,
  canEdit,
  onChange,
}: {
  analyticsEnabled: boolean;
  recordingSummary: string;
  canEdit: boolean;
  onChange: (enabled: boolean) => void;
}) {
  const { t } = useI18n();

  return (
    <>
      <FormGrid>
        <FormField label={t('setup.analytics')}>
          <input
            type="checkbox"
            disabled={!canEdit}
            checked={analyticsEnabled}
            onChange={(e) => onChange(e.target.checked)}
          />
        </FormField>
      </FormGrid>
      <p className="hint">{t('setup.analyticsHint')}</p>
      <p className="hint">{t('setup.analyticsAlarmHint')}</p>
      <p className="basic-recording-summary">{recordingSummary}</p>
    </>
  );
}
