import { useEffect, useMemo, useState } from 'react';
import { journalsApi, type JournalGroupedRow } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';
import { JournalDetailDrawer } from './JournalDetailDrawer';
import { JournalTable } from './JournalTable';
import { useJournalFeed } from './useJournalFeed';
import type { JournalType } from './journalMath';
import { useVisibilityPolling } from '../../hooks/useVisibilityPolling';

function formatLocalDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function today(): string {
  return formatLocalDate(new Date());
}

function yesterday(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return formatLocalDate(d);
}

export function EventsPage() {
  const { t, formatDateTime } = useI18n();
  const { showError } = useToast();
  const [tab, setTab] = useState<JournalType | 'history'>('events');
  const [dateFrom, setDateFrom] = useState(yesterday());
  const [dateTo, setDateTo] = useState(today());
  const [eventType, setEventType] = useState('');
  const [source, setSource] = useState('');
  const [eventTypes, setEventTypes] = useState<string[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [selected, setSelected] = useState<JournalGroupedRow | null>(null);
  const [historyItems, setHistoryItems] = useState<Record<string, unknown>[]>([]);
  const [historyMsg, setHistoryMsg] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [exportTruncated, setExportTruncated] = useState(false);
  const [exporting, setExporting] = useState(false);

  const filters = useMemo(
    () => ({
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      event_type: eventType || undefined,
      source_name: source || undefined,
    }),
    [dateFrom, dateTo, eventType, source],
  );

  const feed = useJournalFeed(tab === 'history' ? 'events' : tab, filters);

  useEffect(() => {
    void journalsApi.filtersMeta().then((meta) => {
      setEventTypes(tab === 'objects' ? meta.event_types_objects : meta.event_types_events);
      setSources(meta.source_names);
    });
  }, [tab]);

  useEffect(() => {
    if (tab !== 'history') return;
    setHistoryLoading(true);
    void journalsApi
      .configHistory()
      .then((h) => {
        if (!h.available) {
          setHistoryMsg(String(h.message ?? t('journals.historyUnavailable')));
          setHistoryItems([]);
          return;
        }
        setHistoryMsg(null);
        setHistoryItems(h.items);
      })
      .finally(() => setHistoryLoading(false));
  }, [tab, t]);

  useVisibilityPolling(() => {
    if (tab === 'history' || selected) return;
    void feed.poll();
  }, 12000, tab !== 'history', 400);

  const onExport = async () => {
    setExporting(true);
    setExportTruncated(false);
    try {
      const { blob, truncated, filename } = await journalsApi.exportDownload(
        tab === 'objects' ? 'objects' : 'events',
        'csv',
        filters,
      );
      setExportTruncated(truncated);
      const href = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = href;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(href);
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    } finally {
      setExporting(false);
    }
  };

  return (
    <section className="panel active">
      <div className="card journal-card">
        <h2>{t('journals.title')}</h2>
        <p className="hint">{t('journals.hint')}</p>
        <div className="journal-tabs">
          <button type="button" className={`journal-tab${tab === 'events' ? ' active' : ''}`} onClick={() => setTab('events')}>
            {t('journals.tabEvents')}
          </button>
          <button type="button" className={`journal-tab${tab === 'objects' ? ' active' : ''}`} onClick={() => setTab('objects')}>
            {t('journals.tabObjects')}
          </button>
          <button type="button" className={`journal-tab${tab === 'history' ? ' active' : ''}`} onClick={() => setTab('history')}>
            {t('journals.tabHistory')}
          </button>
        </div>
        <div className="journal-toolbar toolbar">
          <label className="hint" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            {t('journals.dateFrom')}
            <input
              type="date"
              className="search-input"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </label>
          <label className="hint" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            {t('journals.dateTo')}
            <input type="date" className="search-input" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setDateFrom(today());
              setDateTo(today());
            }}
          >
            {t('journals.presetToday')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setDateFrom(yesterday());
              setDateTo(today());
            }}
          >
            {t('journals.presetTwoDays')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setDateFrom('');
              setDateTo('');
            }}
          >
            {t('journals.allDates')}
          </Button>
          <select className="search-input" value={eventType} onChange={(e) => setEventType(e.target.value)}>
            <option value="">{t('journals.allTypes')}</option>
            {eventTypes.map((et) => (
              <option key={et} value={et}>
                {et}
              </option>
            ))}
          </select>
          {tab === 'objects' ? (
            <select className="search-input" value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">{t('journals.allSources')}</option>
              {sources.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          ) : null}
          <Button variant="outline" onClick={() => void feed.reload()}>
            {t('common.refresh')}
          </Button>
          {tab !== 'history' ? (
            <>
              <Button variant="outline" size="sm" disabled={exporting} onClick={() => void onExport()}>
                {t('common.exportCsv')}
              </Button>
              {exportTruncated ? <span className="hint">{t('journals.exportTruncated')}</span> : null}
            </>
          ) : null}
        </div>
        {tab === 'history' ? (
          historyLoading && !historyItems.length && !historyMsg ? (
            <p className="empty">{t('common.searching')}</p>
          ) : historyMsg ? (
            <p className="empty">{historyMsg}</p>
          ) : (
            <table className="journal-table">
              <thead>
                <tr>
                  <th>{t('journals.colJob')}</th>
                  <th>{t('journals.colProject')}</th>
                  <th>{t('journals.colConfig')}</th>
                  <th>{t('journals.colStatus')}</th>
                  <th>{t('journals.colCreated')}</th>
                </tr>
              </thead>
              <tbody>
                {historyItems.map((item, i) => (
                  <tr key={i}>
                    <td>{String(item.job_id ?? '—')}</td>
                    <td>{String(item.project_id ?? '—')}</td>
                    <td>{String(item.configuration_id ?? '—')}</td>
                    <td>{String(item.status ?? '—')}</td>
                    <td>{formatDateTime(item.creation_time as string | number | null | undefined)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        ) : (
          <>
            {!feed.loading && feed.message ? <p className="empty">{feed.message}</p> : null}
            <JournalTable
              rows={feed.rows}
              journalType={tab}
              onSelect={setSelected}
              emptyText={
                feed.loading && !feed.rows.length
                  ? t('common.searching')
                  : tab === 'events'
                    ? t('journals.emptyEvents')
                    : t('journals.emptyObjects')
              }
            />
            {feed.hasMore ? (
              <Button size="sm" variant="outline" disabled={feed.loading} onClick={() => feed.loadMore()}>
                {t('common.loadMore')}
              </Button>
            ) : null}
          </>
        )}
      </div>
      {selected && tab !== 'history' ? (
        <JournalDetailDrawer row={selected} journalType={tab} onClose={() => setSelected(null)} />
      ) : null}
    </section>
  );
}
