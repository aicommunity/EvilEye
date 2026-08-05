import { createContext, createElement, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { locales, type Locale, type Dict } from './locales';

const STORAGE_KEY = 'evileye.ui.lang';
const warnedKeys = new Set<string>();

const DATE_TIME_OPTS: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
};

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

type I18nCtx = {
  lang: Locale;
  localeTag: 'ru-RU' | 'en-US';
  dateLocaleTag: string;
  setLang: (lang: Locale) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  formatDateTime: (value: number | Date | string | null | undefined) => string;
  formatDate: (value: number | Date | string | null | undefined) => string;
};

const Ctx = createContext<I18nCtx | null>(null);

function readInitial(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'en' || stored === 'ru') return stored;
  } catch {
    /* ignore */
  }
  return 'ru';
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
  const [lang, setLangState] = useState<Locale>(readInitial);

  const setLang = useCallback((next: Locale) => {
    setLangState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  }, []);

  const localeTag: 'ru-RU' | 'en-US' = lang === 'en' ? 'en-US' : 'ru-RU';
  const dateLocaleTag = useMemo(() => resolveDateLocale(lang), [lang]);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const raw = getByPath(locales[lang], key) ?? getByPath(locales.ru, key);
      if (raw == null || typeof raw === 'object') {
        if (import.meta.env.DEV && !warnedKeys.has(key)) {
          warnedKeys.add(key);
          console.warn(`[i18n] missing key: ${key}`);
        }
        return key;
      }
      return interpolate(String(raw), vars);
    },
    [lang],
  );

  const formatDateTime = useCallback(
    (value: number | Date | string | null | undefined) => {
      const d = toDate(value);
      return d ? d.toLocaleString(dateLocaleTag, DATE_TIME_OPTS) : '—';
    },
    [dateLocaleTag],
  );

  const formatDate = useCallback(
    (value: number | Date | string | null | undefined) => {
      const d = toDate(value);
      return d ? d.toLocaleDateString(dateLocaleTag) : '—';
    },
    [dateLocaleTag],
  );

  const value = useMemo(
    () => ({ lang, localeTag, dateLocaleTag, setLang, t, formatDateTime, formatDate }),
    [lang, localeTag, dateLocaleTag, setLang, t, formatDateTime, formatDate],
  );
  return createElement(Ctx.Provider, { value }, children);
}

export function useI18n(): I18nCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useI18n outside I18nProvider');
  return ctx;
}
