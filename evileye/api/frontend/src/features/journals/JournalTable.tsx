import { journalPreviewUrl, type JournalGroupedRow } from '../../api';
import { useI18n } from '../../i18n';
import { eventTypeLabel, redactMediaCredentials, rowKey, type JournalType } from './journalMath';

export function JournalTable({
  rows,
  journalType,
  onSelect,
  emptyText,
}: {
  rows: JournalGroupedRow[];
  journalType: JournalType;
  onSelect: (row: JournalGroupedRow) => void;
  emptyText: string;
}) {
  const { t, formatDateTime } = useI18n();
  if (!rows.length) return <p className="empty">{emptyText}</p>;
  return (
    <div className="journal-table-wrap">
      <table className="journal-table">
        <thead>
          <tr>
            <th>{t('journals.colTime')}</th>
            <th>{t('journals.colEvent')}</th>
            <th>{t('journals.colInfo')}</th>
            <th>{t('journals.colSource')}</th>
            <th>{t('journals.colLost')}</th>
            <th>{t('journals.preview')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const previewPath = row.preview || row.lost_preview;
            const mode = row.preview ? 'found' : 'lost';
            return (
              <tr key={rowKey(row)} className="journal-row" onClick={() => onSelect(row)} style={{ cursor: 'pointer' }}>
                <td>{formatDateTime(row.time as string | null | undefined)}</td>
                <td>{eventTypeLabel(t, String(row.event ?? '—'))}</td>
                <td>{redactMediaCredentials(row.information ?? '—')}</td>
                <td>{redactMediaCredentials(row.source ?? '—')}</td>
                <td>{formatDateTime(row.time_lost as string | null | undefined)}</td>
                <td>
                  {previewPath ? (
                    <img
                      src={journalPreviewUrl({
                        path: String(previewPath),
                        date: row.date_folder,
                        journalType,
                        mode: mode as 'found' | 'lost',
                        w: 96,
                      })}
                      alt=""
                      className="journal-thumb"
                      loading="lazy"
                      decoding="async"
                      style={{ maxWidth: 64, maxHeight: 48 }}
                    />
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
