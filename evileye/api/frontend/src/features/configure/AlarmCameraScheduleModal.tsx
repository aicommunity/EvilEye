import { useEffect, useState } from 'react';
import type { BasicAlarmCamera, AlarmSchedule } from '../../api/setup';
import { Button } from '../../components/ui';
import { useI18n } from '../../i18n';
import { FormField, FormGrid } from './formLayout';
import { WeekdayPicker, PeriodListEditor } from './AlarmScheduleEditor';
import { alarmScheduleMode } from './basicSetupSummaries';

export function AlarmCameraScheduleModal({
  open,
  camera,
  defaultSchedule,
  canEdit,
  onClose,
  onApply,
}: {
  open: boolean;
  camera: BasicAlarmCamera | null;
  defaultSchedule: AlarmSchedule;
  canEdit: boolean;
  onClose: () => void;
  onApply: (cameraId: number, patch: Partial<BasicAlarmCamera>) => void;
}) {
  const { t } = useI18n();
  const [useCustom, setUseCustom] = useState(false);
  const [draft, setDraft] = useState<AlarmSchedule | null>(null);

  useEffect(() => {
    if (!open || !camera) return;
    const hasCustom = Boolean(camera.alarm_schedule);
    setUseCustom(hasCustom);
    setDraft(
      camera.alarm_schedule
        ? { ...camera.alarm_schedule, periods: camera.alarm_schedule.periods.map((p) => [...p] as [string, string]) }
        : {
            enabled: true,
            weekdays: [...(defaultSchedule.weekdays ?? [0, 1, 2, 3, 4, 5, 6])],
            periods: (defaultSchedule.periods ?? [['22:00:00', '06:00:00']]).map(
              (p) => [...p] as [string, string],
            ),
            class_ids: [],
          },
    );
  }, [open, camera, defaultSchedule]);

  if (!open || !camera || !draft) return null;

  const title = t('scheduleAlarm.editCameraTitle', { name: camera.name || `Cam${camera.id + 1}` });

  return (
    <div className="modal open" role="dialog" aria-modal="true">
      <div className="modal-backdrop" onClick={onClose} />
      <div className="modal-content">
        <div className="modal-header">
          <h2>{title}</h2>
          <Button variant="outline" onClick={onClose} aria-label={t('common.close')}>
            &times;
          </Button>
        </div>
        <div className="modal-body">
          <FormField label={t('scheduleAlarm.useCustomInModal')}>
            <input
              type="checkbox"
              disabled={!canEdit}
              checked={useCustom}
              onChange={(e) => setUseCustom(e.target.checked)}
            />
          </FormField>
          {useCustom ? (
            <FormGrid>
              <FormField label={t('scheduleAlarm.weekdaysLabel')}>
                <WeekdayPicker
                  disabled={!canEdit}
                  value={draft.weekdays}
                  onChange={(weekdays) => setDraft({ ...draft, weekdays })}
                />
              </FormField>
              <FormField label={t('scheduleAlarm.periods')}>
                <PeriodListEditor
                  disabled={!canEdit}
                  periods={draft.periods}
                  onChange={(periods) => setDraft({ ...draft, periods })}
                />
              </FormField>
            </FormGrid>
          ) : (
            <p className="hint">{t('scheduleAlarm.scheduleDefault')}</p>
          )}
        </div>
        <div className="modal-footer modal-actions">
          <Button variant="outline" onClick={onClose}>
            {t('setup.cancel')}
          </Button>
          {canEdit ? (
            <Button
              variant="primary"
              onClick={() => {
                onApply(camera.id, useCustom ? { alarm_schedule: draft } : { alarm_schedule: null });
                onClose();
              }}
            >
              {t('setup.apply')}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
