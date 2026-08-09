import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  configsList,
  configGet,
  configCreate,
  configUpdate,
  configDelete,
  stateApi,
  type StateRun,
  ApiError,
  cacheGet,
  cacheSet,
  isAbortError,
} from '../../api';
import { Button, Modal } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useAuth } from '../../auth/AuthContext';
import { useI18n } from '../../i18n';
import { runConfigName, runsHubHref } from './runLinks';

const RUNS_CACHE_KEY = 'state:runs:all';
const RUNS_TTL_MS = 15_000;

type RunsPayload = { current_run?: StateRun | null; items?: StateRun[] };

function countRunsByConfig(payload: RunsPayload | null | undefined): Record<string, number> {
  const counts: Record<string, number> = {};
  if (!payload) return counts;
  const all = [...(payload.items ?? [])];
  if (payload.current_run && !all.some((r) => r.id === payload.current_run!.id)) {
    all.push(payload.current_run);
  }
  for (const r of all) {
    const name = runConfigName(r);
    if (!name) continue;
    counts[name] = (counts[name] ?? 0) + 1;
  }
  return counts;
}

export function ConfigsListPage() {
  const { hasPermission } = useAuth();
  const { showError, showSuccess } = useToast();
  const { t } = useI18n();
  const [names, setNames] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState<{ mode: 'raw' | 'create'; name?: string } | null>(null);
  const [nameInput, setNameInput] = useState('');
  const [body, setBody] = useState('{}');
  const [runCounts, setRunCounts] = useState<Record<string, number>>(() =>
    countRunsByConfig(cacheGet<RunsPayload>(RUNS_CACHE_KEY)),
  );

  const load = useCallback(async () => {
    try {
      setNames(await configsList());
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    }
  }, [showError, t]);

  const loadRuns = useCallback(
    async (signal?: AbortSignal) => {
      if (!hasPermission('runtime:view')) return;
      try {
        const data = (await stateApi.runs('all', { signal })) as RunsPayload;
        if (signal?.aborted) return;
        cacheSet(RUNS_CACHE_KEY, data, RUNS_TTL_MS);
        setRunCounts(countRunsByConfig(data));
      } catch (e) {
        if (isAbortError(e) || signal?.aborted) return;
        // Non-fatal for configs list
      }
    },
    [hasPermission],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const ac = new AbortController();
    void loadRuns(ac.signal);
    return () => ac.abort();
  }, [loadRuns]);

  const openRaw = async (name: string) => {
    setModal({ mode: 'raw', name });
    setNameInput(name);
    try {
      const data = await configGet(name);
      setBody(JSON.stringify(data, null, 2));
    } catch (e) {
      showError(e instanceof ApiError ? e.message : t('common.loadFail'));
    }
  };

  const filtered = names.filter((n) => !search || n.toLowerCase().includes(search.toLowerCase()));

  return (
    <section className="panel active">
      <div className="card">
        <h2>{t('configs.title')}</h2>
        <p className="hint">{t('configs.hint')}</p>
        <div className="toolbar">
          <input className="search-input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('configs.search')} />
          {hasPermission('config:edit') ? (
            <Button
              variant="primary"
              onClick={() => {
                setModal({ mode: 'create' });
                setNameInput('');
                setBody('{}');
              }}
            >
              {t('configs.create')}
            </Button>
          ) : null}
        </div>
        <ul className="configs-list">
          {filtered.map((n) => {
            const count = runCounts[n] ?? 0;
            return (
              <li key={n} className="config-item">
                <span className="config-name">
                  {n}
                  {count > 0 ? (
                    <Link className="config-runs-count" to={runsHubHref({ config: n })}>
                      {t('configs.relatedRunsCount', { count })}
                    </Link>
                  ) : null}
                </span>
                <div className="config-actions">
                  <Link className="btn btn-sm btn-outline" to={`/admin/configs/${encodeURIComponent(n)}`}>
                    {t('configs.studio')}
                  </Link>
                  <Button size="sm" variant="outline" onClick={() => void openRaw(n)}>
                    {t('configs.raw')}
                  </Button>
                  {hasPermission('config:edit') ? (
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() =>
                        void configDelete(n)
                          .then(() => {
                            showSuccess(t('configs.deleted'));
                            return load();
                          })
                          .catch((e) => showError(e.message))
                      }
                    >
                      {t('configs.delete')}
                    </Button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
      <Modal
        open={Boolean(modal)}
        title={modal?.mode === 'create' ? t('configs.newTitle') : t('configs.rawTitle', { name: modal?.name ?? '' })}
        onClose={() => setModal(null)}
        footer={
          hasPermission('config:edit') ? (
            <Button
              variant="primary"
              onClick={() => {
                void (async () => {
                  try {
                    const parsed = JSON.parse(body);
                    if (modal?.mode === 'create') {
                      let fname = nameInput.trim();
                      if (!fname.endsWith('.json')) fname = `${fname}.json`;
                      await configCreate(fname, parsed);
                      showSuccess(t('configs.saved'));
                    } else if (modal?.name) {
                      await configUpdate(modal.name, parsed);
                      showSuccess(t('configs.saved'));
                    }
                    setModal(null);
                    await load();
                  } catch (e) {
                    showError(e instanceof Error ? e.message : t('common.error'));
                  }
                })();
              }}
            >
              {t('configs.save')}
            </Button>
          ) : null
        }
      >
        {modal?.mode === 'create' ? (
          <label className="field">
            <span>{t('configs.fileName')}</span>
            <input value={nameInput} onChange={(e) => setNameInput(e.target.value)} />
          </label>
        ) : null}
        <textarea className="json-editor" value={body} onChange={(e) => setBody(e.target.value)} rows={18} />
      </Modal>
    </section>
  );
}
