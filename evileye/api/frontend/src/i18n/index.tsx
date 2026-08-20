import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { locales, type Locale, type Dict } from './locales';

const STORAGE_KEY = 'evileye.ui.lang';
const DATE_FORMAT_KEY = 'evileye.ui.dateFormat';
const warnedKeys = new Set<string>();

export type DateFormat = 'DD-MM-YYYY' | 'YYYY-MM-DD' | 'MM-DD-YYYY';

const DATE_FORMATS: DateFormat[] = ['DD-MM-YYYY', 'YYYY-MM-DD', 'MM-DD-YYYY'];

function getByPath(dict: Dict, path: string): unknown {
  const parts = path.split('.');
  let cur: unknown = dict;
  for (const p of parts) {
    if (!cur || typeof cur !== 'object') return undefined;
    cur = (cur as Dict)[p];
  }
  return cur;
}

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{\{(\w+)\}\}/g, (_, key: string) => String(vars[key] ?? ''));
}

function resolveDateLocale(uiLang: Locale): string {
  try {
    if (typeof navigator !== 'undefined' && navigator.language) {
      return navigator.language;
    }
  } catch {
    /* ignore */
  }
  return uiLang === 'en' ? 'en-US' : 'ru-RU';
}

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

export function formatDateParts(d: Date, pattern: DateFormat): string {
  const day = pad2(d.getDate());
  const month = pad2(d.getMonth() + 1);
  const year = String(d.getFullYear());
  if (pattern === 'YYYY-MM-DD') return `${year}-${month}-${day}`;
  if (pattern === 'MM-DD-YYYY') return `${month}-${day}-${year}`;
  return `${day}-${month}-${year}`;
}

export function formatTimeParts(d: Date): string {
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}

type I18nCtx = {
  lang: Locale;
  localeTag: 'ru-RU' | 'en-US';
  dateLocaleTag: string;
  dateFormat: DateFormat;
  setLang: (lang: Locale) => void;
  setDateFormat: (format: DateFormat) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  formatDateTime: (value: number | Date | string | null | undefined) => string;
  formatDate: (value: number | Date | string | null | undefined) => string;
  formatTime: (value: number | Date | string | null | undefined) => string;
};

const Ctx = createContext<I18nCtx | null>(null);

function readInitialLang(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'en' || stored === 'ru') return stored;
  } catch {
    /* ignore */
  }
  return 'ru';
}

function readInitialDateFormat(): DateFormat {
  try {
    const stored = localStorage.getItem(DATE_FORMAT_KEY);
    if (stored && DATE_FORMATS.includes(stored as DateFormat)) return stored as DateFormat;
  } catch {
    /* ignore */
  }
  return 'DD-MM-YYYY';
}

function toDate(value: number | Date | string | null | undefined): Date | null {
  if (value == null || value === '') return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value === 'number') {
    const ms = value < 1e12 ? value * 1000 : value;
    const d = new Date(ms);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const raw = String(value).trim();
  const parsed = raw.includes('T') ? raw : raw.replace(' ', 'T');
  const d = new Date(parsed);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Locale>(readInitialLang);
  const [dateFormat, setDateFormatState] = useState<DateFormat>(readInitialDateFormat);
  const langRef = useRef(lang);
  langRef.current = lang;
  const dateFormatRef = useRef(dateFormat);
  dateFormatRef.current = dateFormat;

  const setLang = useCallback((next: Locale) => {
    setLangState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  }, []);

  const setDateFormat = useCallback((next: DateFormat) => {
    setDateFormatState(next);
    try {
      localStorage.setItem(DATE_FORMAT_KEY, next);
    } catch {
      /* ignore */
    }
  }, []);

  const localeTag: 'ru-RU' | 'en-US' = lang === 'en' ? 'en-US' : 'ru-RU';
  const dateLocaleTag = useMemo(() => resolveDateLocale(lang), [lang]);

  // Stable identity: language changes re-render via `lang` in context, but must not
  // invalidate data-fetch callbacks that list `t` in their dependency arrays.
  const t = useCallback((key: string, vars?: Record<string, string | number>) => {
    const current = langRef.current;
    const raw = getByPath(locales[current], key) ?? getByPath(locales.ru, key);
    if (raw == null || typeof raw === 'object') {
      if (import.meta.env.DEV && !warnedKeys.has(key)) {
        warnedKeys.add(key);
        console.warn(`[i18n] missing key: ${key}`);
      }
      return key;
    }
    return interpolate(String(raw), vars);
  }, []);

  const formatDate = useCallback((value: number | Date | string | null | undefined) => {
    const d = toDate(value);
    return d ? formatDateParts(d, dateFormatRef.current) : '—';
  }, []);

  const formatTime = useCallback((value: number | Date | string | null | undefined) => {
    const d = toDate(value);
    return d ? formatTimeParts(d) : '—';
  }, []);

  const formatDateTime = useCallback((value: number | Date | string | null | undefined) => {
    const d = toDate(value);
    if (!d) return '—';
    return `${formatDateParts(d, dateFormatRef.current)} ${formatTimeParts(d)}`;
  }, []);

  const value = useMemo(
    () => ({
      lang,
      localeTag,
      dateLocaleTag,
      dateFormat,
      setLang,
      setDateFormat,
      t,
      formatDateTime,
      formatDate,
      formatTime,
    }),
    [lang, localeTag, dateLocaleTag, dateFormat, setLang, setDateFormat, t, formatDateTime, formatDate, formatTime],
  );
  return createElement(Ctx.Provider, { value }, children);
}

export function useI18n(): I18nCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useI18n outside I18nProvider');
  return ctx;
}
