import { useCallback, useEffect, useMemo, useState } from 'react';
import { editorsApi, type SourceSchedule } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';
import { FormField, FormGrid } from './formLayout';
import { formatInt, INT_STEP, parseIntInput } from './numberFormat';

const WEEKDAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const;

function emptySchedule(): SourceSchedule {
  return {
    enabled: false,
    weekdays: [0, 1, 2, 3, 4, 5, 6],
    periods: [['22:00:00', '06:00:00']],
    class_ids: [],
  };
}

export function WeekdayPicker({
  value,
  onChange,
  disabled,
}: {
  value: number[];
  onChange: (next: number[]) => void;
  disabled?: boolean;
}) {
  const { t } = useI18n();
  const set = useMemo(() => new Set(value), [value]);
  return (
    <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8 }}>
      {WEEKDAY_KEYS.map((key, idx) => (
        <label key={key}>
          <input
            type="checkbox"
            disabled={disabled}
            checked={set.has(idx)}
            onChange={(e) => {
              const next = new Set(set);
              if (e.target.checked) next.add(idx);
              else next.delete(idx);
              onChange([...next].sort((a, b) => a - b));
            }}
          />{' '}
          {t(`scheduleAlarm.weekdays.${key}`)}
        </label>
      ))}
    </div>
  );
}

export function PeriodListEditor({
  periods,
  onChange,
  disabled,
}: {
  periods: [string, string][];
  onChange: (next: [string, string][]) => void;
  disabled?: boolean;
}) {
  const { t } = useI18n();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {periods.map((period, idx) => (
        <div key={idx} className="toolbar" style={{ gap: 8, flexWrap: 'wrap' }}>
          <input
            type="time"
            step={1}
            disabled={disabled}
            value={period[0].slice(0, 8)}
            onChange={(e) => {
              const next = [...periods];
              next[idx] = [`${e.target.value}:00`.slice(0, 8), period[1]];
              onChange(next);
            }}
          />
          <span>—</span>
          <input
            type="time"
            step={1}
            disabled={disabled}
            value={period[1].slice(0, 8)}
            onChange={(e) => {
              const next = [...periods];
              next[idx] = [period[0], `${e.target.value}:00`.slice(0, 8)];
              onChange(next);
            }}
          />
          {!disabled ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => onChange(periods.filter((_, i) => i !== idx))}
            >
              {t('scheduleAlarm.removePeriod')}
            </Button>
          ) : null}
        </div>
      ))}
      {!disabled ? (
        <Button
          size="sm"
          variant="outline"
          onClick={() => onChange([...periods, ['22:00:00', '06:00:00']])}
        >
          {t('scheduleAlarm.addPeriod')}
        </Button>
      ) : null}
    </div>
  );
}

export function AlarmScheduleEditor({
  configName,
  sourceId,
  onSourceIdChange,
  readOnly,
  onSaved,
}: {
  configName: string;
  sourceId: number;
  onSourceIdChange: (id: number) => void;
  readOnly: boolean;
  onSaved?: (restartRequired: boolean) => void;
}) {
  const { t } = useI18n();
  const { showError, showSuccess } = useToast();
  const [mode, setMode] = useState<'default' | 'source'>('default');
  const [schedule, setSchedule] = useState<SourceSchedule>(emptySchedule());
  const [cameraCooldownSec, setCameraCooldownSec] = useState(0);
  const [classMapping, setClassMapping] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [mappingRes, globalRes] = await Promise.all([
        editorsApi.getClassMapping(configName),
        editorsApi.getScheduleAlarm(configName),
      ]);
      setClassMapping(mappingRes.mapping || {});
      setCameraCooldownSec(globalRes.camera_cooldown_sec ?? 0);
      if (mode === 'default') {
        setSchedule(globalRes.default_schedule ?? emptySchedule());
      } else {
        const src = await editorsApi.getSourceScheduleAlarm(configName, sourceId);
        setSchedule(src.schedule ?? emptySchedule());
      }
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [configName, mode, showError, sourceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = () => {
    const run =
      mode === 'default'
        ? editorsApi.putScheduleAlarm(configName, {
            camera_cooldown_sec: cameraCooldownSec,
            default_schedule: schedule,
          })
        : editorsApi.putSourceScheduleAlarm(configName, sourceId, schedule);
    void run
      .then((r) => {
        if (r.restart_required) showSuccess(t('common.savedRestart'));
        else showSuccess(t('common.savedApplied'));
        onSaved?.(Boolean(r.restart_required));
      })
      .catch((e) => showError(e instanceof Error ? e.message : String(e)));
  };

  const classEntries = Object.entries(classMapping);

  if (loading) return <p className="hint">{t('common.loading')}</p>;

  return (
    <div>
      <p className="hint">{t('scheduleAlarm.hint')}</p>
      <FormGrid>
        <FormField label={t('scheduleAlarm.mode')}>
          <select
            value={mode}
            disabled={readOnly}
            onChange={(e) => setMode(e.target.value as 'default' | 'source')}
          >
            <option value="default">{t('scheduleAlarm.modeDefault')}</option>
            <option value="source">{t('scheduleAlarm.modeSource')}</option>
          </select>
        </FormField>
        {mode === 'source' ? (
          <FormField label={t('configure.editors.camera')}>
            <input
              type="number"
              min={0}
              disabled={readOnly}
              value={sourceId}
              onChange={(e) => onSourceIdChange(parseIntInput(e.target.value) ?? 0)}
            />
          </FormField>
        ) : (
          <FormField label={t('scheduleAlarm.cameraCooldown')}>
            <input
              type="number"
              min={0}
              step={INT_STEP}
              disabled={readOnly}
              value={formatInt(cameraCooldownSec)}
              onChange={(e) => setCameraCooldownSec(parseIntInput(e.target.value) ?? 0)}
            />
          </FormField>
        )}
        <FormField label={t('scheduleAlarm.enabled')}>
          <input
            type="checkbox"
            disabled={readOnly}
            checked={schedule.enabled}
            onChange={(e) => setSchedule({ ...schedule, enabled: e.target.checked })}
          />
        </FormField>
        <FormField label={t('scheduleAlarm.weekdaysLabel')}>
          <WeekdayPicker
            value={schedule.weekdays}
            disabled={readOnly}
            onChange={(weekdays) => setSchedule({ ...schedule, weekdays })}
          />
        </FormField>
        <FormField label={t('scheduleAlarm.periods')}>
          <PeriodListEditor
            periods={schedule.periods}
            disabled={readOnly}
            onChange={(periods) => setSchedule({ ...schedule, periods })}
          />
        </FormField>
        {classEntries.length > 0 ? (
          <FormField label={t('scheduleAlarm.classes')}>
            <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8 }}>
              {classEntries.map(([name, id]) => {
                const cid = Number(id);
                const checked = schedule.class_ids.length === 0 || schedule.class_ids.includes(cid);
                return (
                  <label key={name}>
                    <input
                      type="checkbox"
                      disabled={readOnly}
                      checked={checked}
                      onChange={(e) => {
                        const allIds = classEntries.map(([, v]) => Number(v));
                        let next = schedule.class_ids.length === 0 ? [...allIds] : [...schedule.class_ids];
                        if (e.target.checked) {
                          if (!next.includes(cid)) next.push(cid);
                        } else {
                          next = next.filter((x) => x !== cid);
                        }
                        setSchedule({ ...schedule, class_ids: next });
                      }}
                    />{' '}
                    {name}
                  </label>
                );
              })}
            </div>
            <p className="hint">{t('scheduleAlarm.allClassesHint')}</p>
          </FormField>
        ) : null}
      </FormGrid>
      {!readOnly ? (
        <div className="toolbar" style={{ marginTop: 12 }}>
          <Button onClick={() => void save()}>{t('common.save')}</Button>
        </div>
      ) : null}
    </div>
  );
}
