import { useState } from 'react';
import { Link } from 'react-router-dom';
import { type JournalGroupedRow } from '../../api';
import { AuthProvider } from '../../auth/AuthContext';
import { ToastProvider } from '../../components/ui/Toast';
import { Button } from '../../components/ui';
import { useI18n } from '../../i18n';
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
  const { t, lang, setLang, localeTag } = useI18n();
  const feed = useJournalFeed('events', {});
  const [selected, setSelected] = useState<JournalGroupedRow | null>(null);

  usePolling(() => {
    if (!selected) void feed.poll();
  }, 15000);

  return (
    <div className="mobile-shell">
      <header className="mobile-header">
        <strong>EvilEye</strong>
        <nav>
          <Link to="/m/live">{t('mobile.navLive')}</Link> · <Link to="/m/events">{t('mobile.navEvents')}</Link> ·{' '}
          <Link to="/events">{t('mobile.navDesktop')}</Link>
        </nav>
        <select
          aria-label={t('common.language')}
          value={lang}
          onChange={(e) => setLang(e.target.value === 'en' ? 'en' : 'ru')}
          style={{ marginLeft: 8 }}
        >
          <option value="ru">RU</option>
          <option value="en">EN</option>
        </select>
      </header>
      <div className="toolbar" style={{ marginBottom: 8 }}>
        <Button size="sm" variant="outline" style={{ minHeight: 44 }} onClick={() => void feed.reload()}>
          {t('mobile.refresh')}
        </Button>
      </div>
      {!feed.rows.length ? (
        <p className="empty">{t('mobile.noEvents')}</p>
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
                <div style={{ fontWeight: 600 }}>{String(row.event ?? t('journals.eventFallback'))}</div>
                <div className="hint">
                  {formatJournalTime(row.time, localeTag)} · {String(row.source ?? '')}
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
          {t('mobile.more')}
        </Button>
      ) : null}
      {selected ? (
        <JournalDetailDrawer row={selected} journalType="events" onClose={() => setSelected(null)} />
      ) : null}
    </div>
  );
}
