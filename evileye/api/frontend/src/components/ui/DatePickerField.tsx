import { useEffect, useMemo, useRef, useState } from 'react';
import { formatDateParts, useI18n } from '../../i18n';

function parseIsoDate(value: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const dt = new Date(y, mo - 1, d);
  if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return null;
  return dt;
}

function toIsoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function addMonths(d: Date, delta: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + delta, 1);
}

export function DatePickerField({
  value,
  onChange,
  className = '',
  max,
  min,
  id,
  'aria-label': ariaLabel,
}: {
  value: string;
  onChange: (next: string) => void;
  className?: string;
  max?: string;
  min?: string;
  id?: string;
  'aria-label'?: string;
}) {
  const { dateFormat, dateLocaleTag, t } = useI18n();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const selected = parseIsoDate(value);
  const [cursor, setCursor] = useState<Date>(() => startOfMonth(selected ?? new Date()));

  useEffect(() => {
    if (selected) setCursor(startOfMonth(selected));
  }, [value]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const display = selected ? formatDateParts(selected, dateFormat) : value;
  const maxDate = max ? parseIsoDate(max) : null;
  const minDate = min ? parseIsoDate(min) : null;

  const weeks = useMemo(() => {
    const first = startOfMonth(cursor);
    const startPad = (first.getDay() + 6) % 7; // Monday-first
    const days: Array<Date | null> = [];
    for (let i = 0; i < startPad; i += 1) days.push(null);
    const dim = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();
    for (let d = 1; d <= dim; d += 1) {
      days.push(new Date(cursor.getFullYear(), cursor.getMonth(), d));
    }
    while (days.length % 7 !== 0) days.push(null);
    const out: Array<Array<Date | null>> = [];
    for (let i = 0; i < days.length; i += 7) out.push(days.slice(i, i + 7));
    return out;
  }, [cursor]);

  const weekdayLabels = useMemo(() => {
    const base = new Date(2024, 0, 1); // Monday
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(base);
      d.setDate(base.getDate() + i);
      return d.toLocaleDateString(dateLocaleTag, { weekday: 'short' });
    });
  }, [dateLocaleTag]);

  const monthLabel = cursor.toLocaleDateString(dateLocaleTag, { month: 'long', year: 'numeric' });

  const pick = (d: Date) => {
    const iso = toIsoDate(d);
    if (maxDate && d > maxDate) return;
    if (minDate && d < minDate) return;
    onChange(iso);
    setOpen(false);
  };

  const disabledDay = (d: Date) => {
    if (maxDate && d > maxDate) return true;
    if (minDate && d < minDate) return true;
    return false;
  };

  return (
    <div className={`date-picker-field ${className}`.trim()} ref={rootRef} data-testid="date-picker">
      <div className="date-picker-field-row">
        <input
          id={id}
          className="search-input date-picker-input"
          value={display}
          readOnly
          aria-label={ariaLabel}
          onClick={() => setOpen((v) => !v)}
          onFocus={() => setOpen(true)}
        />
        <button
          type="button"
          className="btn btn-outline btn-sm date-picker-toggle"
          aria-label={t('common.openCalendar')}
          onClick={() => setOpen((v) => !v)}
        >
          <span aria-hidden className="date-picker-toggle-icon" />
        </button>
      </div>
      {open ? (
        <div className="date-picker-popover" role="dialog">
          <div className="date-picker-header">
            <button type="button" className="btn btn-outline btn-sm" onClick={() => setCursor((c) => addMonths(c, -1))}>
              ‹
            </button>
            <strong>{monthLabel}</strong>
            <button type="button" className="btn btn-outline btn-sm" onClick={() => setCursor((c) => addMonths(c, 1))}>
              ›
            </button>
          </div>
          <div className="date-picker-weekdays">
            {weekdayLabels.map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>
          <div className="date-picker-grid">
            {weeks.map((week, wi) =>
              week.map((day, di) => {
                if (!day) return <span key={`${wi}-${di}`} className="date-picker-day is-empty" />;
                const iso = toIsoDate(day);
                const isSelected = iso === value;
                const isDisabled = disabledDay(day);
                return (
                  <button
                    key={iso}
                    type="button"
                    className={`date-picker-day${isSelected ? ' is-selected' : ''}${isDisabled ? ' is-disabled' : ''}`}
                    disabled={isDisabled}
                    onClick={() => pick(day)}
                  >
                    {day.getDate()}
                  </button>
                );
              }),
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
