import { describe, expect, it, beforeEach } from 'vitest';
import {
  _resetAuthScopeForTests,
  aclFingerprint,
  bumpAuthScope,
  getAuthEpoch,
  getAuthUsername,
  scopeStillCurrent,
  trackAuthAbort,
  withAuthScope,
} from './authScope';
import { cacheGet, cacheSet } from '../api/dataCache';

describe('authScope (R09)', () => {
  beforeEach(() => {
    _resetAuthScopeForTests();
  });

  it('includes username and epoch in cache keys', () => {
    bumpAuthScope('ops');
    const key = withAuthScope('journals:grouped:events');
    expect(key).toContain('auth:ops|e');
    expect(key).toContain('journals:grouped:events');
    const e1 = getAuthEpoch();
    bumpAuthScope('ops');
    expect(withAuthScope('journals:grouped:events')).not.toBe(key);
    expect(getAuthEpoch()).toBe(e1 + 1);
  });

  it('clears dataCache and aborts tracked controllers on bump', () => {
    bumpAuthScope('admin');
    cacheSet(withAuthScope('x'), { v: 1 }, 60_000);
    expect(cacheGet(withAuthScope('x'))).toEqual({ v: 1 });
    const ac = new AbortController();
    trackAuthAbort(ac);
    const epoch = bumpAuthScope('ops');
    expect(ac.signal.aborted).toBe(true);
    expect(cacheGet(`auth:admin|e${epoch - 1}:x`)).toBeUndefined();
    expect(getAuthUsername()).toBe('ops');
    expect(scopeStillCurrent(epoch)).toBe(true);
    expect(scopeStillCurrent(epoch - 1)).toBe(false);
  });

  it('aclFingerprint changes when cameras shrink', () => {
    expect(aclFingerprint(['Cam1', 'Cam2'], 'restricted')).not.toBe(
      aclFingerprint(['Cam1'], 'restricted'),
    );
  });
});
