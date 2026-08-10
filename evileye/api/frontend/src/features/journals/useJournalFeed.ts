import { useCallback, useEffect, useState } from 'react';
import { journalsApi, type JournalDateFilters, type JournalGroupedRow, cacheGet, cacheSet, isAbortError } from '../../api';
import { useI18n } from '../../i18n';
import { mergePrependRows, type JournalType } from './journalMath';

const GROUPED_TTL_MS = 12_000;

function groupedCacheKey(tab: JournalType, filters: JournalDateFilters, page: number): string {
  return `journals:grouped:${tab}:${filters.date_from ?? ''}:${filters.date_to ?? ''}:${filters.date ?? ''}:${filters.source_name ?? ''}:${filters.event_type ?? ''}:p${page}`;
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

  const load = useCallback(
    async (append = false) => {
      const ac = new AbortController();
      setLoading(true);
      try {
        const nextPage = append ? page + 1 : 0;
        const res =
          tab === 'events'
            ? await journalsApi.eventsGrouped(nextPage, 30, filters, { signal: ac.signal })
            : await journalsApi.objectsGrouped(nextPage, 30, filters, { signal: ac.signal });
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
        if (isAbortError(e)) return;
        throw e;
      } finally {
        setLoading(false);
      }
    },
    [tab, filters, page],
  );

  const reload = useCallback(async (signal?: AbortSignal) => {
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
    try {
      const res =
        tab === 'events'
          ? await journalsApi.eventsGrouped(0, 30, filters, { signal })
          : await journalsApi.objectsGrouped(0, 30, filters, { signal });
      if (signal?.aborted) return;
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
      if (isAbortError(e) || signal?.aborted) return;
      throw e;
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [tab, filters]);

  const poll = useCallback(async () => {
    try {
      const res =
        tab === 'events'
          ? await journalsApi.eventsGrouped(0, 30, filters)
          : await journalsApi.objectsGrouped(0, 30, filters);
      if (!res.available) return;
      cacheSet(groupedCacheKey(tab, filters, 0), res, GROUPED_TTL_MS);
      setRows((prev) => mergePrependRows(prev, res.items).rows);
    } catch {
      /* ignore */
    }
  }, [tab, filters]);

  useEffect(() => {
    const ac = new AbortController();
    void reload(ac.signal);
    return () => ac.abort();
  }, [tab, filters.source_name, filters.event_type, filters.date, filters.date_from, filters.date_to]); // eslint-disable-line react-hooks/exhaustive-deps

  return { rows, hasMore, message, loading, loadMore: () => void load(true), reload: () => void reload(), poll };
}
