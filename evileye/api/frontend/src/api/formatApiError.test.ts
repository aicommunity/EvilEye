import { describe, expect, it } from 'vitest';
import { ApiError } from './client';
import { formatApiError, isTimeoutApiError } from './formatApiError';

const t = (key: string) => key;

describe('formatApiError', () => {
  it('maps playback timeout detail to i18n key', () => {
    const err = new ApiError(503, 'playback_segments timeout');
    expect(formatApiError(err, t)).toBe('playback.loadTimeout');
  });

  it('maps state timeout detail to serverBusy', () => {
    const err = new ApiError(503, 'state_cameras timeout');
    expect(formatApiError(err, t)).toBe('common.serverBusy');
  });

  it('passes through non-timeout messages', () => {
    const err = new ApiError(400, 'camera or cameras query required');
    expect(formatApiError(err, t)).toBe('camera or cameras query required');
  });
});

describe('isTimeoutApiError', () => {
  it('detects 503 and timeout messages', () => {
    expect(isTimeoutApiError(new ApiError(503, 'x'))).toBe(true);
    expect(isTimeoutApiError(new ApiError(500, 'playback_timeline timeout'))).toBe(true);
    expect(isTimeoutApiError(new ApiError(400, 'bad'))).toBe(false);
  });
});
