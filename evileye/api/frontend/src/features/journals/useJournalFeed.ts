import { useCallback, useEffect, useState } from 'react';
import { journalsApi, type JournalGroupedRow } from '../../api';
import { useI18n } from '../../i18n';
import { mergePrependRows, type JournalType } from './journalMath';

export function useJournalFeed(tab: JournalType, filters: { source_name?: string; event_type?: string; date?: string }) {
  const { t } = useI18n();
  const [rows, setRows] = useState<JournalGroupedRow[]>([]);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(
    async (append = false) => {
      setLoading(true);
      try {
        const nextPage = append ? page + 1 : 0;
        const res =
          tab === 'events'
            ? await journalsApi.eventsGrouped(nextPage, 30, filters)
            : await journalsApi.objectsGrouped(nextPage, 30, filters);
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
      } finally {
        setLoading(false);
      }
    },
    [tab, filters, page, t],
  );

  const reload = useCallback(async () => {
    setPage(0);
    setLoading(true);
    try {
      const res =
        tab === 'events'
          ? await journalsApi.eventsGrouped(0, 30, filters)
          : await journalsApi.objectsGrouped(0, 30, filters);
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
    } finally {
      setLoading(false);
    }
  }, [tab, filters, t]);

  const poll = useCallback(async () => {
    try {
      const res =
        tab === 'events'
          ? await journalsApi.eventsGrouped(0, 30, filters)
          : await journalsApi.objectsGrouped(0, 30, filters);
      if (!res.available) return;
      setRows((prev) => mergePrependRows(prev, res.items).rows);
    } catch {
      /* ignore */
    }
  }, [tab, filters]);

  useEffect(() => {
    void reload();
  }, [tab, filters.source_name, filters.event_type, filters.date]); // eslint-disable-line react-hooks/exhaustive-deps

  return { rows, hasMore, message, loading, loadMore: () => void load(true), reload, poll };
}
