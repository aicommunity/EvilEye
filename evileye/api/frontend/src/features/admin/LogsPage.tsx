import { useCallback, useEffect, useRef, useState } from 'react';
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
  const [view, setView] = useState<{ name: string; content: string; live: boolean } | null>(null);
  const esRef = useRef<EventSource | null>(null);

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

  useEffect(() => {
    return () => {
      esRef.current?.close();
      esRef.current = null;
    };
  }, []);

  const openStatic = (name: string) => {
    esRef.current?.close();
    esRef.current = null;
    void logsApi
      .read(name, 500)
      .then((p) => setView({ name: p.name, content: p.content, live: false }))
      .catch((e) => showError(e instanceof ApiError ? e.message : 'Ошибка'));
  };

  const openLive = (name: string) => {
    esRef.current?.close();
    const es = new EventSource(logsApi.streamUrl(name, 400));
    esRef.current = es;
    setView({ name, content: 'Подключение…', live: true });
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as { content?: string; name?: string };
        setView({ name: data.name ?? name, content: data.content ?? '', live: true });
      } catch {
        /* ignore */
      }
    };
    es.onerror = () => {
      showError('SSE логов прерван');
      es.close();
    };
  };

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
                <th />
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr key={f.name} className="log-file-row">
                  <td onClick={() => openStatic(f.name)} style={{ cursor: 'pointer' }}>
                    {f.name}
                  </td>
                  <td>{formatBytes(f.size_bytes)}</td>
                  <td>{new Date(f.updated_at * 1000).toLocaleString('ru-RU')}</td>
                  <td>
                    <Button size="sm" variant="outline" onClick={() => openLive(f.name)}>
                      Live
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <Modal
        open={Boolean(view)}
        title={view ? `${view.name}${view.live ? ' (live)' : ''}` : 'Лог'}
        onClose={() => {
          esRef.current?.close();
          esRef.current = null;
          setView(null);
        }}
        wide
      >
        <pre className="log-view-pre">{view?.content}</pre>
      </Modal>
    </section>
  );
}
