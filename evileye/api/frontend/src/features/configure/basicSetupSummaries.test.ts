import { describe, expect, it } from 'vitest';
import {
  alarmSummary,
  formatCaptureSourceLabel,
  formatPeriodsShort,
  formatWeekdaysShort,
  recordingSummary,
  sourcesSummary,
} from './basicSetupSummaries';

const t = (key: string, params?: Record<string, string | number>) => {
  const map: Record<string, string> = {
    'scheduleAlarm.weekdays.mon': 'Пн',
    'scheduleAlarm.weekdays.tue': 'Вт',
    'scheduleAlarm.weekdays.wed': 'Ср',
    'scheduleAlarm.weekdays.thu': 'Чт',
    'scheduleAlarm.weekdays.fri': 'Пт',
    'scheduleAlarm.weekdays.sat': 'Сб',
    'scheduleAlarm.weekdays.sun': 'Вс',
    'setup.sourcesSummary': '{{capture}} захват · {{logical}} камер',
    'setup.recordingSummaryOn': 'Запись: {{names}}',
    'setup.recordingSummaryOff': 'Запись выключена',
    'scheduleAlarm.summaryNeedsAnalytics': 'Требуется аналитика',
    'scheduleAlarm.summaryDisabled': 'Выкл',
    'scheduleAlarm.summaryEnabled': 'Вкл · {{active}}/{{total}} камер · {{days}} {{times}}',
    'scheduleAlarm.summaryCustomCount': ' · {{count}} своих',
  };
  let out = map[key] ?? key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      out = out.replace(`{{${k}}}`, String(v));
    }
  }
  return out;
};

describe('basicSetupSummaries', () => {
  it('formats all weekdays as range', () => {
    expect(formatWeekdaysShort([0, 1, 2, 3, 4, 5, 6], t)).toBe('Пн–Вс');
  });

  it('formats work week as range', () => {
    expect(formatWeekdaysShort([0, 1, 2, 3, 4], t)).toBe('Пн–Пт');
  });

  it('formats sparse weekdays', () => {
    expect(formatWeekdaysShort([0, 2, 4], t)).toBe('Пн, Ср, Пт');
  });

  it('formats periods short', () => {
    expect(formatPeriodsShort([['22:00:00', '06:00:00']])).toBe('22:00–06:00');
  });

  it('sources summary with split', () => {
    expect(
      sourcesSummary(
        [
          { id: 0, name: 'Cam1', type: 'IpCamera', address: '' },
          { id: 1, name: 'Cam2', extra_names: ['Cam3'], logical_ids: [1, 2], type: 'IpCamera', address: '' },
        ],
        [
          { source_id: 0, source_name: 'Cam1' },
          { source_id: 1, source_name: 'Cam2' },
          { source_id: 2, source_name: 'Cam3' },
        ],
        t,
      ),
    ).toBe('2 захват · 3 камер');
  });

  it('formats capture source label with extras joined by +', () => {
    expect(formatCaptureSourceLabel({ id: 0, name: 'Cam1', type: 'IpCamera', address: '' })).toBe('Cam1');
    expect(
      formatCaptureSourceLabel({
        id: 1,
        name: 'Cam2',
        extra_names: ['Cam3'],
        logical_ids: [1, 2],
        type: 'IpCamera',
        address: '',
      }),
    ).toBe('Cam2+Cam3');
  });

  it('recording summary joins split cameras with + and omits count', () => {
    expect(
      recordingSummary(
        [
          { id: 0, name: 'Cam1', record: true, type: 'IpCamera', address: '' },
          {
            id: 1,
            name: 'Cam2',
            extra_names: ['Cam3'],
            logical_ids: [1, 2],
            record: true,
            type: 'IpCamera',
            address: '',
          },
          {
            id: 3,
            name: 'Cam4',
            extra_names: ['Cam5'],
            logical_ids: [3, 4],
            record: true,
            type: 'IpCamera',
            address: '',
          },
        ],
        t,
      ),
    ).toBe('Запись: Cam1, Cam2+Cam3, Cam4+Cam5');
  });

  it('recording summary off when no sources record', () => {
    expect(
      recordingSummary([{ id: 0, name: 'Cam1', record: false, type: 'IpCamera', address: '' }], t),
    ).toBe('Запись выключена');
  });

  it('alarm summary needs analytics', () => {
    expect(alarmSummary({ enabled: true, weekdays: [], periods: [], class_ids: [] }, [], false, t)).toBe(
      'Требуется аналитика',
    );
  });

  it('alarm summary enabled with custom count', () => {
    const out = alarmSummary(
      {
        enabled: true,
        weekdays: [0, 1, 2, 3, 4, 5, 6],
        periods: [['22:00:00', '06:00:00']],
        class_ids: [],
      },
      [
        { id: 0, name: 'Cam1', alarm_enabled: true },
        { id: 1, name: 'Cam2', alarm_enabled: true, alarm_schedule: { enabled: true, weekdays: [0], periods: [], class_ids: [] } },
        { id: 2, name: 'Cam3', alarm_enabled: false },
      ],
      true,
      t,
    );
    expect(out).toContain('2/3');
    expect(out).toContain('1 своих');
  });
});
