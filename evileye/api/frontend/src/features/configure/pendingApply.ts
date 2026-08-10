const PREFIX = 'evileye.config.pendingApply.';

export function pendingApplyStorageKey(configName: string): string {
  return `${PREFIX}${configName}`;
}

export function readPendingApply(configName: string): boolean {
  try {
    return sessionStorage.getItem(pendingApplyStorageKey(configName)) === '1';
  } catch {
    return false;
  }
}

export function writePendingApply(configName: string, pending: boolean): void {
  try {
    const key = pendingApplyStorageKey(configName);
    if (pending) sessionStorage.setItem(key, '1');
    else sessionStorage.removeItem(key);
  } catch {
    /* ignore quota / private mode */
  }
}
