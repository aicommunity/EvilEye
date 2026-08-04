import { useEffect, useState } from 'react';
import { journalsApi } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useAuth } from '../../auth/AuthContext';

export function ConfigHistoryPanel({ configName }: { configName?: string }) {
  const { hasPermission } = useAuth();
  const { showError, showSuccess } = useToast();
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [compare, setCompare] = useState<{
    left: string;
    right: string;
    differences: unknown;
    jobA: number;
    jobB: number;
  } | null>(null);
  const canRestore = hasPermission('history:edit') || hasPermission('config:edit');

  const reload = () => {
    void journalsApi.configHistory().then((h) => {
      if (!h.available) {
        setMsg(String(h.message ?? 'История недоступна'));
        return;
      }
      setMsg(null);
      setItems(h.items);
    });
  };

  useEffect(() => {
    reload();
  }, []);

  const toggle = (jobId: number) => {
    setSelected((prev) => {
      if (prev.includes(jobId)) return prev.filter((x) => x !== jobId);
      if (prev.length >= 2) return [prev[1], jobId];
      return [...prev, jobId];
    });
  };

  return (
    <div>
      {msg ? <p className="empty">{msg}</p> : null}
      <div className="toolbar">
        <Button
          size="sm"
          variant="outline"
          disabled={selected.length !== 2}
          onClick={() =>
            void journalsApi
              .compareHistory(selected[0], selected[1])
              .then((r) => {
                if (r.error) {
                  showError(String(r.error));
                  return;
                }
                setCompare({
                  jobA: selected[0],
                  jobB: selected[1],
                  left: JSON.stringify(r.left ?? {}, null, 2),
                  right: JSON.stringify(r.right ?? {}, null, 2),
                  differences: r.differences ?? [],
                });
              })
              .catch((e) => showError(e.message))
          }
        >
          Сравнить (2)
        </Button>
        <Button size="sm" variant="outline" onClick={reload}>
          Обновить
        </Button>
        {compare ? (
          <Button size="sm" variant="outline" onClick={() => setCompare(null)}>
            Скрыть diff
          </Button>
        ) : null}
      </div>
      {compare ? (
        <div>
          <p className="hint">
            Job #{compare.jobA} vs #{compare.jobB} · differences:{' '}
            {Array.isArray(compare.differences) ? compare.differences.length : '—'}
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <pre className="log-view-pre" style={{ maxHeight: 320, overflow: 'auto' }}>
              {compare.left}
            </pre>
            <pre className="log-view-pre" style={{ maxHeight: 320, overflow: 'auto' }}>
              {compare.right}
            </pre>
          </div>
          <details style={{ marginTop: 8 }}>
            <summary>Список отличий</summary>
            <pre className="log-view-pre" style={{ maxHeight: 160, overflow: 'auto' }}>
              {JSON.stringify(compare.differences, null, 2)}
            </pre>
          </details>
        </div>
      ) : null}
      <table className="journal-table">
        <thead>
          <tr>
            <th />
            <th>Job</th>
            <th>Config</th>
            <th>Status</th>
            <th>Created</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((item, i) => {
            const jobId = Number(item.job_id);
            return (
              <tr key={i}>
                <td>
                  <input
                    type="checkbox"
                    checked={selected.includes(jobId)}
                    onChange={() => toggle(jobId)}
                    disabled={!Number.isFinite(jobId)}
                  />
                </td>
                <td>{String(item.job_id ?? '—')}</td>
                <td>{String(item.configuration_id ?? '—')}</td>
                <td>{String(item.status ?? '—')}</td>
                <td>{String(item.creation_time ?? '—')}</td>
                <td>
                  {canRestore && configName && Number.isFinite(jobId) ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        void journalsApi
                          .restoreHistory(jobId, configName)
                          .then(() => showSuccess(`Восстановлено в ${configName}`))
                          .catch((e) => showError(e.message))
                      }
                    >
                      Restore
                    </Button>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
