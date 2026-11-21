import type { BasicAlarmCamera, AlarmSchedule } from '../../api/setup';
import { Button } from '../../components/ui';
import { useI18n } from '../../i18n';
import { FormField, FormGrid } from './formLayout';
import { WeekdayPicker, PeriodListEditor } from './AlarmScheduleEditor';
import { alarmScheduleMode } from './basicSetupSummaries';

export function BasicAlarmScheduleSection({
  canEdit,
  analyticsDisabled,
  alarmSchedule,
  alarmCameras,
  onUpdateSchedule,
  onUpdateCamera,
  onOpenCameraModal,
}: {
  canEdit: boolean;
  analyticsDisabled: boolean;
  alarmSchedule: AlarmSchedule;
  alarmCameras: BasicAlarmCamera[];
  onUpdateSchedule: (patch: Partial<AlarmSchedule>) => void;
  onUpdateCamera: (cameraId: number, patch: Partial<BasicAlarmCamera>) => void;
  onOpenCameraModal: (cameraId: number) => void;
}) {
  const { t } = useI18n();
  const controlsDisabled = !canEdit || analyticsDisabled;

  return (
    <>
      <p className="hint">{t('scheduleAlarm.basicHint')}</p>
      <p className="hint">{t('scheduleAlarm.logicalCamerasHint')}</p>

      <FormGrid>
        <FormField label={t('scheduleAlarm.enabled')}>
          <input
            type="checkbox"
            disabled={controlsDisabled}
            checked={Boolean(alarmSchedule.enabled)}
            onChange={(e) => onUpdateSchedule({ enabled: e.target.checked })}
          />
        </FormField>
      </FormGrid>

      <div className="basic-alarm-default-schedule">
        <h4 className="basic-alarm-subtitle">{t('scheduleAlarm.defaultScheduleTitle')}</h4>
        <FormGrid>
          <FormField label={t('scheduleAlarm.weekdaysLabel')}>
            <WeekdayPicker
              disabled={controlsDisabled}
              value={alarmSchedule.weekdays ?? [0, 1, 2, 3, 4, 5, 6]}
              onChange={(weekdays) => onUpdateSchedule({ weekdays })}
            />
          </FormField>
          <FormField label={t('scheduleAlarm.periods')}>
            <PeriodListEditor
              disabled={controlsDisabled}
              periods={alarmSchedule.periods ?? [['22:00:00', '06:00:00']]}
              onChange={(periods) => onUpdateSchedule({ periods })}
            />
          </FormField>
        </FormGrid>
      </div>

      <h4 className="basic-alarm-subtitle">{t('scheduleAlarm.camerasLabel')}</h4>
      {alarmCameras.length > 0 ? (
        <div className="basic-alarm-table-wrap">
          <table className="basic-alarm-table journal-table">
            <thead>
              <tr>
                <th>{t('scheduleAlarm.colCamera')}</th>
                <th>{t('scheduleAlarm.colParticipate')}</th>
                <th>{t('scheduleAlarm.colSchedule')}</th>
                <th>{t('scheduleAlarm.colActions')}</th>
              </tr>
            </thead>
            <tbody>
              {alarmCameras.map((cam) => {
                const mode = alarmScheduleMode(cam);
                return (
                  <tr key={cam.id}>
                    <td>{cam.name || `Cam${cam.id + 1}`}</td>
                    <td>
                      <input
                        type="checkbox"
                        disabled={controlsDisabled}
                        checked={cam.alarm_enabled !== false}
                        onChange={(e) =>
                          onUpdateCamera(cam.id, {
                            alarm_enabled: e.target.checked,
                            ...(e.target.checked ? {} : { alarm_schedule: null }),
                          })
                        }
                      />
                    </td>
                    <td>
                      {mode === 'none' ? (
                        '—'
                      ) : (
                        <select
                          className="basic-alarm-schedule-select"
                          disabled={controlsDisabled}
                          value={mode === 'custom' ? 'custom' : 'default'}
                          onChange={(e) => {
                            if (e.target.value === 'custom') {
                              onUpdateCamera(cam.id, {
                                alarm_schedule: {
                                  enabled: true,
                                  weekdays: alarmSchedule.weekdays ?? [0, 1, 2, 3, 4, 5, 6],
                                  periods: alarmSchedule.periods ?? [['22:00:00', '06:00:00']],
                                  class_ids: [],
                                },
                              });
                              onOpenCameraModal(cam.id);
                            } else {
                              onUpdateCamera(cam.id, { alarm_schedule: null });
                            }
                          }}
                        >
                          <option value="default">{t('scheduleAlarm.scheduleDefault')}</option>
                          <option value="custom">{t('scheduleAlarm.scheduleCustom')}</option>
                        </select>
                      )}
                    </td>
                    <td>
                      {mode === 'custom' ? (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={controlsDisabled}
                          onClick={() => onOpenCameraModal(cam.id)}
                        >
                          {t('scheduleAlarm.configure')}
                        </Button>
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="hint">{t('scheduleAlarm.noCamerasYet')}</p>
      )}
      <p className="hint">{t('scheduleAlarm.camerasHint')}</p>
      {!alarmSchedule.enabled ? (
        <p className="hint">{t('scheduleAlarm.camerasDisabledHint')}</p>
      ) : null}
    </>
  );
}
