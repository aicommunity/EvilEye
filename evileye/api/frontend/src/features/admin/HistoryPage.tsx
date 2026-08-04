import { useCallback, useEffect, useState } from 'react';
import { stateApi, type StateRun } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';

export function HistoryPage() {
  const { showError } = useToast();
  const [runs, setRuns] = useState<StateRun[]>([]);

  const load = useCallback(async () => {
    try {
      const data = (await stateApi.runs('history')) as { items: StateRun[] };
      setRuns(data.items ?? []);
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Ошибка');
    }
  }, [showError]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="panel active">
      <div className="card">
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>История запусков</h2>
          <Button variant="outline" onClick={() => void load()}>
            Обновить
          </Button>
        </div>
        {!runs.length ? (
          <p className="empty">Нет записей истории запусков.</p>
        ) : (
          <table className="journal-table">
            <thead>
              <tr>
                <th>id</th>
                <th>name</th>
                <th>pipeline_class</th>
                <th>state</th>
                <th>pid</th>
                <th>error</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.name ?? '—'}</td>
                  <td>{r.pipeline_class ?? '—'}</td>
                  <td>{r.state}</td>
                  <td>{r.pid ?? '—'}</td>
                  <td>{r.error ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
