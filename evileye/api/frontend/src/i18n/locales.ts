import type { Dict } from './locales/ru';
import ru from './locales/ru';
import en from './locales/en';

export type Locale = 'ru' | 'en';
export type { Dict };

export const locales: Record<Locale, Dict> = { ru, en };
