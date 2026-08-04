import { useEffect, useMemo, useState } from 'react';
import { journalsApi, type JournalGroupedRow } from '../../api';
import { Button } from '../../components/ui';
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
        setHistoryMsg(String(h.message ?? 'История недоступна'));
        setHistoryItems([]);
        return;
      }
      setHistoryMsg(null);
      setHistoryItems(h.items);
    });
  }, [tab]);

  usePolling(() => {
    if (tab === 'history' || selected) return;
    void feed.poll();
  }, 3000, tab !== 'history');

  const exportHref = journalsApi.exportUrl(tab === 'objects' ? 'objects' : 'events', 'csv', filters);

  return (
    <section className="panel active">
      <div className="card journal-card">
        <h2>Журналы</h2>
        <p className="hint">События, объекты и история конфигураций</p>
        <div className="journal-tabs">
          <button type="button" className={`journal-tab${tab === 'events' ? ' active' : ''}`} onClick={() => setTab('events')}>
            События
          </button>
          <button type="button" className={`journal-tab${tab === 'objects' ? ' active' : ''}`} onClick={() => setTab('objects')}>
            Объекты
          </button>
          <button type="button" className={`journal-tab${tab === 'history' ? ' active' : ''}`} onClick={() => setTab('history')}>
            История конфигураций
          </button>
        </div>
        <div className="journal-toolbar toolbar">
          <input type="date" className="search-input" value={date} onChange={(e) => setDate(e.target.value)} />
          <Button size="sm" variant="outline" onClick={() => setDate('')}>
            Все даты
          </Button>
          <select className="search-input" value={eventType} onChange={(e) => setEventType(e.target.value)}>
            <option value="">Все типы</option>
            {eventTypes.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          {tab === 'objects' ? (
            <select className="search-input" value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">Все источники</option>
              {sources.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          ) : null}
          <Button variant="outline" onClick={() => void feed.reload()}>
            Обновить
          </Button>
          {tab !== 'history' ? (
            <a className="btn btn-outline btn-sm" href={exportHref}>
              Export CSV
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
                  <th>Job</th>
                  <th>Project</th>
                  <th>Config</th>
                  <th>Status</th>
                  <th>Created</th>
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
              emptyText={tab === 'events' ? 'События не найдены.' : 'Объекты не найдены.'}
            />
            {feed.hasMore ? (
              <Button size="sm" variant="outline" disabled={feed.loading} onClick={() => feed.loadMore()}>
                Загрузить ещё
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
