import { journalPreviewUrl, type JournalGroupedRow } from '../../api';
import { formatJournalTime, rowKey, type JournalType } from './journalMath';

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
  if (!rows.length) return <p className="empty">{emptyText}</p>;
  return (
    <div className="journal-table-wrap">
      <table className="journal-table">
        <thead>
          <tr>
            <th>Время</th>
            <th>Событие</th>
            <th>Информация</th>
            <th>Источник</th>
            <th>Потерян</th>
            <th>Preview</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const previewPath = row.preview || row.lost_preview;
            const mode = row.preview ? 'found' : 'lost';
            return (
              <tr key={rowKey(row)} className="journal-row" onClick={() => onSelect(row)} style={{ cursor: 'pointer' }}>
                <td>{formatJournalTime(row.time)}</td>
                <td>{String(row.event ?? '—')}</td>
                <td>{String(row.information ?? '—')}</td>
                <td>{String(row.source ?? '—')}</td>
                <td>{formatJournalTime(row.time_lost)}</td>
                <td>
                  {previewPath ? (
                    <img
                      src={journalPreviewUrl({
                        path: String(previewPath),
                        date: row.date_folder,
                        journalType,
                        mode: mode as 'found' | 'lost',
                      })}
                      alt=""
                      className="journal-thumb"
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
