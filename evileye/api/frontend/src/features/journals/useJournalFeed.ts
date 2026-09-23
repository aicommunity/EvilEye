import { useCallback, useEffect, useRef, useState } from 'react';
import {
  journalsApi,
  type JournalDateFilters,
  type JournalGroupedRow,
  cacheGet,
  cacheSet,
  formatApiError,
  isAbortError,
} from '../../api';
import { getAuthEpoch, onAuthScopeChange, trackAuthAbort, withAuthScope } from '../../auth/authScope';
import { useI18n } from '../../i18n';
import { mergePrependRows, type JournalType } from './journalMath';

const GROUPED_TTL_MS = 12_000;
const GROUPED_LOAD_TIMEOUT_MS = 30_000;

function groupedCacheKey(tab: JournalType, filters: JournalDateFilters, page: number): string {
  return withAuthScope(
    `journals:grouped:${tab}:${filters.date_from ?? ''}:${filters.date_to ?? ''}:${filters.date ?? ''}:${filters.source_name ?? ''}:${filters.event_type ?? ''}:p${page}`,
  );
}

/** B04: ignore delayed responses after filter switch / abort. */
export function shouldApplyJournalResult(gen: number, currentGen: number, aborted: boolean): boolean {
  return !aborted && gen === currentGen;
}

function abortAny(signals: AbortSignal[]): AbortSignal {
  const ac = new AbortController();
  const onAbort = () => ac.abort();
  for (const s of signals) {
    if (s.aborted) {
      ac.abort();
      return ac.signal;
    }
    s.addEventListener('abort', onAbort, { once: true });
  }
  return ac.signal;
}

export function useJournalFeed(tab: JournalType, filters: JournalDateFilters) {
  const { t } = useI18n();
  const initialKey = groupedCacheKey(tab, filters, 0);
  const initial = cacheGet<{ items: JournalGroupedRow[]; available: boolean; message?: string }>(initialKey);
  const [rows, setRows] = useState<JournalGroupedRow[]>(() => (initial?.available ? initial.items : []));
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(() => (initial?.available ? (initial.items?.length ?? 0) >= 30 : true));
  const [message, setMessage] = useState<string | null>(() =>
    initial && !initial.available ? String(initial.message ?? null) : null,
  );
  const [loading, setLoading] = useState(() => !initial);
  const generationRef = useRef(0);
  const loadAbortRef = useRef<AbortController | null>(null);

  const load = useCallback(
    async (append = false) => {
      if (append && loading) return;
      loadAbortRef.current?.abort();
      const ac = new AbortController();
      loadAbortRef.current = ac;
      const untrack = trackAuthAbort(ac);
      const epochAtStart = getAuthEpoch();
      const gen = ++generationRef.current;
      const timeoutAc = new AbortController();
      const timeoutId = window.setTimeout(() => timeoutAc.abort(), GROUPED_LOAD_TIMEOUT_MS);
      const effective = abortAny([ac.signal, timeoutAc.signal]);
      setLoading(true);
      try {
        const nextPage = append ? page + 1 : 0;
        const res =
          tab === 'events'
            ? await journalsApi.eventsGrouped(nextPage, 30, filters, { signal: effective })
            : await journalsApi.objectsGrouped(nextPage, 30, filters, { signal: effective });
        if (epochAtStart !== getAuthEpoch()) return;
        if (!shouldApplyJournalResult(gen, generationRef.current, effective.aborted)) return;
        if (!append) cacheSet(groupedCacheKey(tab, filters, 0), res, GROUPED_TTL_MS);
        if (!res.available) {
          setRows([]);
          setMessage(String(res.message ?? t('journals.unavailable')));
          setHasMore(false);
          return;
        }
        setMessage(null);
        setRows((prev) => (append ? [...prev, ...res.items] : res.items));
        setPage(nextPage);
        setHasMore(res.items.length >= 30);
      } catch (e) {
        if (
          epochAtStart !== getAuthEpoch() ||
          !shouldApplyJournalResult(gen, generationRef.current, effective.aborted || isAbortError(e))
        ) {
          return;
        }
        if (!append) {
          setMessage(formatApiError(e, t));
        }
      } finally {
        window.clearTimeout(timeoutId);
        untrack();
        if (gen === generationRef.current) setLoading(false);
      }
    },
    [tab, filters, page, t, loading],
  );

  const reload = useCallback(
    async (signal?: AbortSignal) => {
      generationRef.current += 1;
      const gen = generationRef.current;
      const epochAtStart = getAuthEpoch();
      setPage(0);
      const cached = cacheGet<{ items: JournalGroupedRow[]; available: boolean; message?: string }>(
        groupedCacheKey(tab, filters, 0),
      );
      if (cached) {
        if (!cached.available) {
          setRows([]);
          setMessage(String(cached.message ?? t('journals.unavailable')));
          setHasMore(false);
        } else {
          setMessage(null);
          setRows(cached.items);
          setHasMore(cached.items.length >= 30);
        }
        setLoading(false);
      } else {
        setLoading(true);
      }
      const timeoutAc = new AbortController();
      const localAc = new AbortController();
      const untrack = trackAuthAbort(localAc);
      const timeoutId = window.setTimeout(() => timeoutAc.abort(), GROUPED_LOAD_TIMEOUT_MS);
      const signals = signal
        ? [signal, timeoutAc.signal, localAc.signal]
        : [timeoutAc.signal, localAc.signal];
      const effective = abortAny(signals);
      try {
        const res =
          tab === 'events'
            ? await journalsApi.eventsGrouped(0, 30, filters, { signal: effective })
            : await journalsApi.objectsGrouped(0, 30, filters, { signal: effective });
        if (epochAtStart !== getAuthEpoch()) return;
        if (!shouldApplyJournalResult(gen, generationRef.current, effective.aborted)) return;
        cacheSet(groupedCacheKey(tab, filters, 0), res, GROUPED_TTL_MS);
        if (!res.available) {
          setRows([]);
          setMessage(String(res.message ?? t('journals.unavailable')));
          setHasMore(false);
          return;
        }
        setMessage(null);
        setRows(res.items);
        setPage(0);
        setHasMore(res.items.length >= 30);
      } catch (e) {
        if (
          epochAtStart !== getAuthEpoch() ||
          !shouldApplyJournalResult(gen, generationRef.current, effective.aborted || isAbortError(e))
        ) {
          return;
        }
        if (!cached?.items?.length) {
          setMessage(formatApiError(e, t));
        } else {
          setMessage(t('journals.loadError'));
        }
      } finally {
        window.clearTimeout(timeoutId);
        untrack();
        if (gen === generationRef.current) setLoading(false);
      }
    },
    [tab, filters, t],
  );

  const pollInFlightRef = useRef(false);
  const pollAbortRef = useRef<AbortController | null>(null);

  const poll = useCallback(async () => {
    if (pollInFlightRef.current || loading) return;
    const gen = generationRef.current;
    const epochAtStart = getAuthEpoch();
    pollAbortRef.current?.abort();
    const ac = new AbortController();
    pollAbortRef.current = ac;
    const untrack = trackAuthAbort(ac);
    const timeoutAc = new AbortController();
    const timeoutId = window.setTimeout(() => timeoutAc.abort(), GROUPED_LOAD_TIMEOUT_MS);
    const effective = abortAny([ac.signal, timeoutAc.signal]);
    pollInFlightRef.current = true;
    try {
      const res =
        tab === 'events'
          ? await journalsApi.eventsGrouped(0, 30, filters, { signal: effective })
          : await journalsApi.objectsGrouped(0, 30, filters, { signal: effective });
      if (epochAtStart !== getAuthEpoch()) return;
      if (!shouldApplyJournalResult(gen, generationRef.current, effective.aborted)) return;
      if (!res.available) return;
      cacheSet(groupedCacheKey(tab, filters, 0), res, GROUPED_TTL_MS);
      setRows((prev) => mergePrependRows(prev, res.items).rows);
    } catch {
      /* ignore */
    } finally {
      window.clearTimeout(timeoutId);
      untrack();
      pollInFlightRef.current = false;
    }
  }, [tab, filters, loading]);

  useEffect(() => {
    const ac = new AbortController();
    void reload(ac.signal);
    return () => {
      ac.abort();
      loadAbortRef.current?.abort();
      pollAbortRef.current?.abort();
      generationRef.current += 1;
    };
  }, [tab, filters.source_name, filters.event_type, filters.date, filters.date_from, filters.date_to]); // eslint-disable-line react-hooks/exhaustive-deps

  // F06: clear displayed rows and reload when auth epoch changes.
  useEffect(() => {
    return onAuthScopeChange(() => {
      setRows([]);
      setMessage(null);
      loadAbortRef.current?.abort();
      pollAbortRef.current?.abort();
      generationRef.current += 1;
      void reload();
    });
  }, [reload]);

  return { rows, hasMore, message, loading, loadMore: () => void load(true), reload: () => void reload(), poll };
}
