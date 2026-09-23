/**
 * Central auth scope for SPA caches and in-flight fetches (audit R09).
 * Cache keys and request guards must include authEpoch + username.
 */

import { cacheClear } from '../api/dataCache';

let authEpoch = 0;
let authUsername = '';
const scopeListeners = new Set<() => void>();
const inflightAborts = new Set<AbortController>();
const scopeCleanups = new Set<() => void>();

export function getAuthEpoch(): number {
  return authEpoch;
}

export function getAuthUsername(): string {
  return authUsername;
}

/** Prefix for sensitive cache keys: `auth:{user}|e{epoch}:...` */
export function authScopePrefix(): string {
  const user = authUsername || 'anon';
  return `auth:${user}|e${authEpoch}`;
}

export function withAuthScope(key: string): string {
  return `${authScopePrefix()}:${key}`;
}

export function scopeStillCurrent(epochAtStart: number): boolean {
  return epochAtStart === authEpoch;
}

export function onAuthScopeChange(listener: () => void): () => void {
  scopeListeners.add(listener);
  return () => {
    scopeListeners.delete(listener);
  };
}

/** Register a sync cleanup (stores) invoked on every bumpAuthScope. */
export function registerAuthScopeCleanup(fn: () => void): () => void {
  scopeCleanups.add(fn);
  return () => {
    scopeCleanups.delete(fn);
  };
}

/** Track an AbortController; aborted automatically on next bumpAuthScope. */
export function trackAuthAbort(ac: AbortController): () => void {
  inflightAborts.add(ac);
  return () => {
    inflightAborts.delete(ac);
  };
}

/**
 * Bump epoch, clear SPA dataCache, abort tracked fetches, notify listeners.
 * Call on login, logout, 401, and ACL revision for the same user.
 */
export function bumpAuthScope(nextUsername?: string | null): number {
  authEpoch += 1;
  if (nextUsername !== undefined) {
    authUsername = nextUsername ? String(nextUsername) : '';
  }
  cacheClear();
  for (const ac of [...inflightAborts]) {
    try {
      ac.abort();
    } catch {
      /* ignore */
    }
  }
  inflightAborts.clear();
  for (const cleanup of [...scopeCleanups]) {
    try {
      cleanup();
    } catch {
      /* ignore */
    }
  }
  for (const listener of [...scopeListeners]) {
    try {
      listener();
    } catch {
      /* ignore */
    }
  }
  return authEpoch;
}

/** Sync username without bump (initial identity before first bump). */
export function setAuthUsername(username: string | null | undefined): void {
  authUsername = username ? String(username) : '';
}

export function aclFingerprint(
  allowedCameras: string[] | undefined,
  cameraAccess: string | undefined,
): string {
  const cams = [...(allowedCameras ?? [])].map(String).sort().join(',');
  return `${cameraAccess ?? ''}|${cams}`;
}

/** Test helper: reset module state. */
export function _resetAuthScopeForTests(): void {
  authEpoch = 0;
  authUsername = '';
  scopeListeners.clear();
  inflightAborts.clear();
}
