import { useEffect, useState } from 'react';
import { journalsApi } from '../../api';

export function ConfigHistoryPanel() {
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    void journalsApi.configHistory().then((h) => {
      if (!h.available) {
        setMsg(String(h.message ?? 'История недоступна'));
        return;
      }
      setItems(h.items);
    });
  }, []);

  if (msg) return <p className="empty">{msg}</p>;
  return (
    <table className="journal-table">
      <thead>
        <tr>
          <th>Job</th>
          <th>Config</th>
          <th>Status</th>
          <th>Created</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item, i) => (
          <tr key={i}>
            <td>{String(item.job_id ?? '—')}</td>
            <td>{String(item.configuration_id ?? '—')}</td>
            <td>{String(item.status ?? '—')}</td>
            <td>{String(item.creation_time ?? '—')}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
