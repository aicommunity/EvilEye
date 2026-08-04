import { useEffect, useMemo, useState } from 'react';
import { journalsApi, type JournalGroupedRow } from '../../api';
import { Button } from '../../components/ui';
import { useI18n } from '../../i18n';
import { JournalDetailDrawer } from './JournalDetailDrawer';
import { JournalTable } from './JournalTable';
import { useJournalFeed } from './useJournalFeed';
import type { JournalType } from './journalMath';
import { usePolling } from '../../hooks/usePolling';

function today(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

export function EventsPage() {
  const { t } = useI18n();
  const [tab, setTab] = useState<JournalType | 'history'>('events');
  const [date, setDate] = useState(today());
  const [eventType, setEventType] = useState('');
  const [source, setSource] = useState('');
  const [eventTypes, setEventTypes] = useState<string[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [selected, setSelected] = useState<JournalGroupedRow | null>(null);
  const [historyItems, setHistoryItems] = useState<Record<string, unknown>[]>([]);
  const [historyMsg, setHistoryMsg] = useState<string | null>(null);

  const filters = useMemo(
    () => ({
      date: date || undefined,
      event_type: eventType || undefined,
      source_name: source || undefined,
    }),
    [date, eventType, source],
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
    void journalsApi.configHistory().then((h) => {
      if (!h.available) {
        setHistoryMsg(String(h.message ?? t('journals.historyUnavailable')));
        setHistoryItems([]);
        return;
      }
      setHistoryMsg(null);
      setHistoryItems(h.items);
    });
  }, [tab, t]);

  usePolling(() => {
    if (tab === 'history' || selected) return;
    void feed.poll();
  }, 3000, tab !== 'history');

  const exportHref = journalsApi.exportUrl(tab === 'objects' ? 'objects' : 'events', 'csv', filters);

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
          <input type="date" className="search-input" value={date} onChange={(e) => setDate(e.target.value)} />
          <Button size="sm" variant="outline" onClick={() => setDate('')}>
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
            <a className="btn btn-outline btn-sm" href={exportHref}>
              {t('common.exportCsv')}
            </a>
          ) : null}
        </div>
        {tab === 'history' ? (
          historyMsg ? (
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
                    <td>{String(item.creation_time ?? '—')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        ) : (
          <>
            {feed.message ? <p className="empty">{feed.message}</p> : null}
            <JournalTable
              rows={feed.rows}
              journalType={tab}
              onSelect={setSelected}
              emptyText={tab === 'events' ? t('journals.emptyEvents') : t('journals.emptyObjects')}
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
