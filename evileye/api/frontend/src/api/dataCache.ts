/** Lightweight process-local stale-while-revalidate cache for SPA section data. */

type CacheEntry = {
  value: unknown;
  expiresAt: number;
};

const store = new Map<string, CacheEntry>();
const MAX_KEYS = 256;

function evictExpiredAndOverflow(): void {
  const now = Date.now();
  for (const [key, entry] of store) {
    if (entry.expiresAt <= now) store.delete(key);
  }
  while (store.size > MAX_KEYS) {
    const oldest = store.keys().next().value;
    if (oldest == null) break;
    store.delete(oldest);
  }
}

export function cacheGet<T>(key: string): T | undefined {
  const entry = store.get(key);
  if (!entry) return undefined;
  if (Date.now() > entry.expiresAt) {
    store.delete(key);
    return undefined;
  }
  return entry.value as T;
}

export function cacheIsFresh(key: string): boolean {
  const entry = store.get(key);
  if (!entry) return false;
  return Date.now() <= entry.expiresAt;
}

export function cacheSet<T>(key: string, value: T, ttlMs: number): void {
  store.delete(key); // refresh insertion order for FIFO eviction
  store.set(key, { value, expiresAt: Date.now() + Math.max(0, ttlMs) });
  evictExpiredAndOverflow();
}

export function cacheInvalidate(keyOrPrefix: string): void {
  if (store.has(keyOrPrefix)) {
    store.delete(keyOrPrefix);
    return;
  }
  for (const key of [...store.keys()]) {
    if (key.startsWith(keyOrPrefix)) store.delete(key);
  }
}

export function cacheClear(): void {
  store.clear();
}

/**
 * Return stale (or fresh) cached value immediately; always revalidate via fetcher
 * unless the entry is still fresh and `skipIfFresh` is true.
 */
export async function swrFetch<T>(
  key: string,
  ttlMs: number,
  fetcher: () => Promise<T>,
  opts?: { signal?: AbortSignal; skipIfFresh?: boolean },
): Promise<{ data: T; fromCache: boolean }> {
  const cached = cacheGet<T>(key);
  if (cached !== undefined && opts?.skipIfFresh && cacheIsFresh(key)) {
    return { data: cached, fromCache: true };
  }
  if (opts?.signal?.aborted) {
    if (cached !== undefined) return { data: cached, fromCache: true };
    throw new DOMException('Aborted', 'AbortError');
  }
  const data = await fetcher();
  if (!opts?.signal?.aborted) {
    cacheSet(key, data, ttlMs);
  }
  return { data, fromCache: false };
}

export function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === 'AbortError') ||
    (err instanceof Error && err.name === 'AbortError')
  );
}
