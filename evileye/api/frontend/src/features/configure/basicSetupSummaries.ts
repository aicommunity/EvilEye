import type { BasicAlarmCamera, BasicSetup, AlarmSchedule } from '../../api/setup';
import type { ConfigCameraOption } from './cameraList';
import type { SetupStatus } from '../../api/setup';

const WEEKDAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const;

type TFn = (key: string, params?: Record<string, string | number>) => string;

export function formatWeekdaysShort(weekdays: number[], t: TFn): string {
  const sorted = [...new Set(weekdays)].sort((a, b) => a - b);
  if (sorted.length === 0) return '—';
  if (sorted.length === 7) {
    return `${t('scheduleAlarm.weekdays.mon')}–${t('scheduleAlarm.weekdays.sun')}`;
  }

  const runs: number[][] = [];
  let run: number[] = [];
  for (const day of sorted) {
    if (!run.length || day === run[run.length - 1] + 1) {
      run.push(day);
    } else {
      runs.push(run);
      run = [day];
    }
  }
  if (run.length) runs.push(run);

  return runs
    .map((r) => {
      if (r.length >= 3) {
        return `${t(`scheduleAlarm.weekdays.${WEEKDAY_KEYS[r[0]]}`)}–${t(`scheduleAlarm.weekdays.${WEEKDAY_KEYS[r[r.length - 1]]}`)}`;
      }
      return r.map((d) => t(`scheduleAlarm.weekdays.${WEEKDAY_KEYS[d]}`)).join(', ');
    })
    .join(', ');
}

export function formatPeriodsShort(periods: [string, string][]): string {
  if (!periods.length) return '—';
  return periods
    .map(([from, to]) => `${from.slice(0, 5)}–${to.slice(0, 5)}`)
    .join(', ');
}

export function systemSummary(basic: BasicSetup, status: SetupStatus | null | undefined, t: TFn): string {
  const dir = String(basic.data_dir || '').trim();
  const storage =
    basic.storage_mode === 'database' ? t('setup.storageDbShort') : t('setup.storageJsonShort');
  if (!dir && status?.needs_setup) return t('setup.summaryNotConfigured');
  return dir ? `${dir} · ${storage}` : storage;
}

export function sourcesSummary(
  sources: BasicSetup['sources'],
  pipelineCameras: ConfigCameraOption[],
  t: TFn,
): string {
  const capture = sources.length;
  const logical =
    pipelineCameras.length ||
    sources.reduce((n, s) => n + (s.logical_ids?.length ? s.logical_ids.length : 1), 0);
  return t('setup.sourcesSummary', { capture, logical });
}

export function analyticsSummary(basic: BasicSetup, recordingSummary: string, t: TFn): string {
  const base = basic.analytics_enabled ? t('setup.analyticsSummaryOn') : t('setup.analyticsSummaryOff');
  return `${base} · ${recordingSummary}`;
}

export function alarmSummary(
  schedule: AlarmSchedule | null | undefined,
  alarmCameras: BasicAlarmCamera[],
  analyticsEnabled: boolean,
  t: TFn,
): string {
  if (!analyticsEnabled) return t('scheduleAlarm.summaryNeedsAnalytics');
  if (!schedule?.enabled) return t('scheduleAlarm.summaryDisabled');

  const total = alarmCameras.length;
  const active = alarmCameras.filter((c) => c.alarm_enabled !== false).length;
  const days = formatWeekdaysShort(schedule.weekdays ?? [], t);
  const times = formatPeriodsShort(schedule.periods ?? []);
  const customCount = alarmCameras.filter((c) => c.alarm_schedule).length;

  let out = t('scheduleAlarm.summaryEnabled', { active, total, days, times });
  if (customCount > 0) {
    out += t('scheduleAlarm.summaryCustomCount', { count: customCount });
  }
  return out;
}

export type AlarmScheduleMode = 'none' | 'default' | 'custom';

export function alarmScheduleMode(cam: BasicAlarmCamera): AlarmScheduleMode {
  if (cam.alarm_enabled === false) return 'none';
  if (cam.alarm_schedule) return 'custom';
  return 'default';
}
