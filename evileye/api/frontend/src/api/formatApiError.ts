import { ApiError } from './client';

type Translate = (key: string, params?: Record<string, string | number>) => string;

/** True when the API timed out or returned a busy/503 timeout detail. */
export function isTimeoutApiError(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  if (error.status === 503) return true;
  return /timeout/i.test(error.message || '');
}

/**
 * Map raw API detail strings (e.g. `playback_segments timeout`) to i18n copy.
 * Falls back to the original message for non-timeout errors.
 */
export function formatApiError(error: unknown, t: Translate): string {
  if (error instanceof ApiError) {
    const detail = String(error.message || '').toLowerCase();
    if (error.status === 503 || detail.includes('timeout')) {
      if (detail.includes('playback')) return t('playback.loadTimeout');
      return t('common.serverBusy');
    }
    return error.message || t('common.error');
  }
  if (error instanceof Error && error.message) return error.message;
  return t('common.error');
}
