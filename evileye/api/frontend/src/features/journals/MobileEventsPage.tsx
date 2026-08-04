import { useState } from 'react';
import { Link } from 'react-router-dom';
import { type JournalGroupedRow } from '../../api';
import { AuthProvider } from '../../auth/AuthContext';
import { ToastProvider } from '../../components/ui/Toast';
import { Button } from '../../components/ui';
import { JournalDetailDrawer } from './JournalDetailDrawer';
import { useJournalFeed } from './useJournalFeed';
import { formatJournalTime } from './journalMath';
import { usePolling } from '../../hooks/usePolling';

export function MobileEventsPage() {
  return (
    <AuthProvider>
      <ToastProvider>
        <MobileEventsInner />
      </ToastProvider>
    </AuthProvider>
  );
}

function MobileEventsInner() {
  const feed = useJournalFeed('events', {});
  const [selected, setSelected] = useState<JournalGroupedRow | null>(null);

  usePolling(() => {
    if (!selected) void feed.poll();
  }, 4000);

  return (
    <div className="mobile-shell">
      <header className="mobile-header">
        <strong>EvilEye</strong>
        <nav>
          <Link to="/m/live">Live</Link> · <Link to="/m/events">Events</Link> · <Link to="/events">Desktop</Link>
        </nav>
      </header>
      <div className="toolbar" style={{ marginBottom: 8 }}>
        <Button size="sm" variant="outline" style={{ minHeight: 44 }} onClick={() => void feed.reload()}>
          Обновить
        </Button>
      </div>
      {!feed.rows.length ? (
        <p className="empty">Нет событий</p>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {feed.rows.map((row) => (
            <li key={String(row.row_key ?? `${row.time}-${row.event}`)}>
              <button
                type="button"
                onClick={() => setSelected(row)}
                style={{
                  width: '100%',
                  textAlign: 'left',
                  minHeight: 56,
                  padding: '12px 14px',
                  marginBottom: 8,
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  background: 'var(--bg-card)',
                  color: 'inherit',
                  cursor: 'pointer',
                }}
              >
                <div style={{ fontWeight: 600 }}>{String(row.event ?? 'Событие')}</div>
                <div className="hint">
                  {formatJournalTime(row.time)} · {String(row.source ?? '')}
                </div>
                <div className="hint" style={{ marginTop: 4 }}>
                  {String(row.information ?? '').slice(0, 120)}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
      {feed.hasMore ? (
        <Button variant="outline" style={{ minHeight: 44, width: '100%' }} onClick={() => void feed.loadMore()}>
          Ещё
        </Button>
      ) : null}
      {selected ? (
        <JournalDetailDrawer row={selected} journalType="events" onClose={() => setSelected(null)} />
      ) : null}
    </div>
  );
}
