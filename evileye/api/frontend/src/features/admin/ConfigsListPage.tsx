import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  configsList,
  configCreate,
  configDelete,
  stateApi,
  type StateRun,
  cacheGet,
  cacheSet,
  isAbortError,
} from '../../api';
import { Button, Modal } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useAuth } from '../../auth/AuthContext';
import { useI18n } from '../../i18n';
import { runConfigName, runsHubHref } from './runLinks';
import { restartConfigRun } from '../configure/restartConfigRun';

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
  const canRun = hasPermission('runtime:control');
  const [names, setNames] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [nameInput, setNameInput] = useState('');
  const [body, setBody] = useState('{}');
  const [runsPayload, setRunsPayload] = useState<RunsPayload | null>(
    () => cacheGet<RunsPayload>(RUNS_CACHE_KEY) ?? null,
  );
  const [runCounts, setRunCounts] = useState<Record<string, number>>(() =>
    countRunsByConfig(cacheGet<RunsPayload>(RUNS_CACHE_KEY)),
  );
  const [startingName, setStartingName] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setNames(await configsList());
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    }
  }, [showError]);

  const loadRuns = useCallback(
    async (signal?: AbortSignal) => {
      if (!hasPermission('runtime:view') && !canRun) return;
      try {
        const data = (await stateApi.runs('all', { signal })) as RunsPayload;
        if (signal?.aborted) return;
        cacheSet(RUNS_CACHE_KEY, data, RUNS_TTL_MS);
        setRunsPayload(data);
        setRunCounts(countRunsByConfig(data));
      } catch (e) {
        if (isAbortError(e) || signal?.aborted) return;
      }
    },
    [canRun, hasPermission],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const ac = new AbortController();
    void loadRuns(ac.signal);
    return () => ac.abort();
  }, [loadRuns]);

  const handleStart = async (name: string) => {
    if (!canRun) return;
    let payload = runsPayload;
    try {
      payload = (await stateApi.runs('all')) as RunsPayload;
      cacheSet(RUNS_CACHE_KEY, payload, RUNS_TTL_MS);
      setRunsPayload(payload);
      setRunCounts(countRunsByConfig(payload));
    } catch {
      /* use cached */
    }
    const current = payload?.current_run ?? null;
    const currentName = current ? runConfigName(current) : null;
    const alive = Boolean(current && (current.alive || current.state === 'running' || current.state === 'starting'));
    let msg = t('configs.startConfirm', { name });
    if (alive && currentName && currentName !== name) {
      msg = t('configs.startConfirmReplace', { current: currentName, name });
    } else if (alive && currentName === name) {
      msg = t('configs.startConfirmRestart', { name });
    }
    if (!window.confirm(msg)) return;
    setStartingName(name);
    try {
      await restartConfigRun(name);
      showSuccess(t('configs.started'));
      void loadRuns();
    } catch (e) {
      showError(e instanceof Error ? e.message : t('configs.startFailed'));
    } finally {
      setStartingName(null);
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
                setModalOpen(true);
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
                  {canRun ? (
                    <Button size="sm" variant="primary" disabled={startingName === n} onClick={() => void handleStart(n)}>
                      {t('configs.start')}
                    </Button>
                  ) : null}
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
        open={modalOpen}
        title={t('configs.newTitle')}
        onClose={() => setModalOpen(false)}
        footer={
          hasPermission('config:edit') ? (
            <Button
              variant="primary"
              onClick={() => {
                void (async () => {
                  try {
                    const parsed = JSON.parse(body);
                    let fname = nameInput.trim();
                    if (!fname.endsWith('.json')) fname = `${fname}.json`;
                    await configCreate(fname, parsed);
                    showSuccess(t('configs.saved'));
                    setModalOpen(false);
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
        <label className="field">
          <span>{t('configs.fileName')}</span>
          <input value={nameInput} onChange={(e) => setNameInput(e.target.value)} />
        </label>
        <textarea className="json-editor" value={body} onChange={(e) => setBody(e.target.value)} rows={18} />
      </Modal>
    </section>
  );
}
