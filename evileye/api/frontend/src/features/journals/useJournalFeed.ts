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
import { useI18n } from '../../i18n';
import { mergePrependRows, type JournalType } from './journalMath';

const GROUPED_TTL_MS = 12_000;
const GROUPED_LOAD_TIMEOUT_MS = 30_000;

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
  const generationRef = useRef(0);
  const loadAbortRef = useRef<AbortController | null>(null);

  const load = useCallback(
    async (append = false) => {
      if (append && loading) return;
      loadAbortRef.current?.abort();
      const ac = new AbortController();
      loadAbortRef.current = ac;
      const gen = ++generationRef.current;
      const timeoutId = window.setTimeout(() => ac.abort(), GROUPED_LOAD_TIMEOUT_MS);
      setLoading(true);
      try {
        const nextPage = append ? page + 1 : 0;
        const res =
          tab === 'events'
            ? await journalsApi.eventsGrouped(nextPage, 30, filters, { signal: ac.signal })
            : await journalsApi.objectsGrouped(nextPage, 30, filters, { signal: ac.signal });
        if (gen !== generationRef.current || ac.signal.aborted) return;
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
        if (isAbortError(e) || ac.signal.aborted || gen !== generationRef.current) {
          if (!append && !rows.length) setMessage(t('journals.loadError'));
          return;
        }
        if (!append) {
          setMessage(formatApiError(e, t));
        }
      } finally {
        window.clearTimeout(timeoutId);
        if (gen === generationRef.current) setLoading(false);
      }
    },
    [tab, filters, page, rows.length, t, loading],
  );

  const reload = useCallback(
    async (signal?: AbortSignal) => {
      generationRef.current += 1;
      const gen = generationRef.current;
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
      const localAc = signal ? null : new AbortController();
      const effective = signal ?? localAc!.signal;
      const timeoutId = window.setTimeout(() => {
        if (!signal) localAc?.abort();
      }, GROUPED_LOAD_TIMEOUT_MS);
      try {
        const res =
          tab === 'events'
            ? await journalsApi.eventsGrouped(0, 30, filters, { signal: effective })
            : await journalsApi.objectsGrouped(0, 30, filters, { signal: effective });
        if (effective.aborted || gen !== generationRef.current) return;
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
        if (isAbortError(e) || effective.aborted || gen !== generationRef.current) {
          if (!cached?.available && !(cached?.items?.length)) {
            setMessage(t('journals.loadError'));
          }
          return;
        }
        if (!cached?.items?.length) {
          setMessage(formatApiError(e, t));
        } else {
          setMessage(t('journals.loadError'));
        }
      } finally {
        window.clearTimeout(timeoutId);
        if (gen === generationRef.current && !effective.aborted) setLoading(false);
      }
    },
    [tab, filters, t],
  );

  const poll = useCallback(async () => {
    const gen = generationRef.current;
    try {
      const res =
        tab === 'events'
          ? await journalsApi.eventsGrouped(0, 30, filters)
          : await journalsApi.objectsGrouped(0, 30, filters);
      if (gen !== generationRef.current) return;
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
    return () => {
      ac.abort();
      loadAbortRef.current?.abort();
      generationRef.current += 1;
    };
  }, [tab, filters.source_name, filters.event_type, filters.date, filters.date_from, filters.date_to]); // eslint-disable-line react-hooks/exhaustive-deps

  return { rows, hasMore, message, loading, loadMore: () => void load(true), reload: () => void reload(), poll };
}
