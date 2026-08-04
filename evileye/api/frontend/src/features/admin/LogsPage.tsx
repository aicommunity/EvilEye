import { useCallback, useEffect, useState } from 'react';
import { logsApi, ApiError } from '../../api';
import { Button, Modal } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function LogsPage() {
  const { showError } = useToast();
  const [files, setFiles] = useState<Array<{ name: string; updated_at: number; size_bytes: number }>>([]);
  const [view, setView] = useState<{ name: string; content: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await logsApi.list();
      setFiles(res.files ?? []);
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Ошибка логов');
    }
  }, [showError]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="panel active">
      <div className="card">
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>Логи</h2>
          <Button variant="outline" onClick={() => void load()}>
            Обновить
          </Button>
        </div>
        {!files.length ? (
          <p className="empty">Технические логи недоступны.</p>
        ) : (
          <table className="journal-table log-files-table">
            <thead>
              <tr>
                <th>Файл</th>
                <th>Размер</th>
                <th>Обновлён</th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr
                  key={f.name}
                  className="log-file-row"
                  onClick={() =>
                    void logsApi
                      .read(f.name)
                      .then((p) => setView({ name: p.name, content: p.content }))
                      .catch((e) => showError(e instanceof ApiError ? e.message : 'Ошибка'))
                  }
                >
                  <td>{f.name}</td>
                  <td>{formatBytes(f.size_bytes)}</td>
                  <td>{new Date(f.updated_at * 1000).toLocaleString('ru-RU')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <Modal open={Boolean(view)} title={view?.name ?? 'Лог'} onClose={() => setView(null)} wide>
        <pre className="log-view-pre">{view?.content}</pre>
      </Modal>
    </section>
  );
}
