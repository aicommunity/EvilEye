import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { logsApi, ApiError, cacheGet, cacheSet, isAbortError } from '../../api';
import { Button, Modal } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

const LOGS_CACHE_KEY = 'logs:list';
const LOGS_TTL_MS = 15_000;

type LogsList = { available: boolean; files: Array<{ name: string; updated_at: number; size_bytes: number }> };

export function LogsPage() {
  const { showError } = useToast();
  const { t, formatDateTime } = useI18n();
  const [searchParams] = useSearchParams();
  const queryFile = searchParams.get('file');
  const cached = cacheGet<LogsList>(LOGS_CACHE_KEY);
  const [files, setFiles] = useState<Array<{ name: string; updated_at: number; size_bytes: number }>>(
    () => cached?.files ?? [],
  );
  const [loading, setLoading] = useState(() => !cached?.files?.length);
  const filesRef = useRef(files);
  filesRef.current = files;
  const [view, setView] = useState<{ name: string; content: string; live: boolean } | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const openedQueryRef = useRef<string | null>(null);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!filesRef.current.length && !cacheGet(LOGS_CACHE_KEY)) setLoading(true);
      try {
        const res = await logsApi.list(50, { signal });
        if (signal?.aborted) return;
        cacheSet(LOGS_CACHE_KEY, res, LOGS_TTL_MS);
        setFiles(res.files ?? []);
      } catch (e) {
        if (isAbortError(e) || signal?.aborted) return;
        showError(e instanceof Error ? e.message : t('logs.title'));
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [showError],
  );

  useEffect(() => {
    const ac = new AbortController();
    void load(ac.signal);
    return () => ac.abort();
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
      .catch((e) => showError(e instanceof ApiError ? e.message : t('common.error')));
  };

  const openLive = useCallback(
    (name: string) => {
      esRef.current?.close();
      const es = new EventSource(logsApi.streamUrl(name, 400));
      esRef.current = es;
      setView({ name, content: t('logs.connecting'), live: true });
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data) as { content?: string; append?: string; name?: string };
          setView((prev) => {
            const nextName = data.name ?? name;
            if (data.append != null && prev && prev.name === nextName && prev.content !== t('logs.connecting')) {
              return { name: nextName, content: prev.content + data.append, live: true };
            }
            return { name: nextName, content: data.content ?? data.append ?? '', live: true };
          });
        } catch {
          /* ignore */
        }
      };
      es.onerror = () => {
        showError(t('logs.sseError'));
        es.close();
      };
    },
    [showError, t],
  );

  useEffect(() => {
    if (!queryFile) {
      openedQueryRef.current = null;
      return;
    }
    if (loading) return;
    if (openedQueryRef.current === queryFile) return;
    openedQueryRef.current = queryFile;
    const safe = queryFile.includes('/') || queryFile.includes('..') ? null : queryFile;
    if (!safe) {
      showError(t('logs.fileNotFound'));
      return;
    }
    const known = files.some((f) => f.name === safe);
    if (!known) {
      // Still try follow — file may exist but outside list limit / freshly created.
      void logsApi
        .read(safe, 1)
        .then(() => openLive(safe))
        .catch(() => showError(t('logs.fileNotFound')));
      return;
    }
    openLive(safe);
  }, [queryFile, loading, files, openLive, showError]);

  return (
    <section className="panel active">
      <div className="card">
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>{t('logs.title')}</h2>
          <Button variant="outline" onClick={() => void load()}>
            {t('logs.refresh')}
          </Button>
        </div>
        {queryFile ? <p className="hint">{t('logs.openFromQuery', { name: queryFile })}</p> : null}
        {!files.length ? (
          <p className="empty">{loading ? t('common.searching') : t('logs.empty')}</p>
        ) : (
          <table className="journal-table log-files-table">
            <thead>
              <tr>
                <th>{t('logs.file')}</th>
                <th>{t('logs.size')}</th>
                <th>{t('logs.updated')}</th>
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
                  <td>{formatDateTime(f.updated_at)}</td>
                  <td>
                    <Button size="sm" variant="outline" onClick={() => openLive(f.name)}>
                      {t('logs.follow')}
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
        title={view ? view.name : t('logs.title')}
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
