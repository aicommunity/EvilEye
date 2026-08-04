import { useCallback, useEffect, useState } from 'react';
import {
  configsList,
  runsList,
  runCreate,
  runStart,
  runStop,
  runDelete,
  type ConfigRun,
  ApiError,
} from '../../api';
import { Badge, Button, Modal } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useAuth } from '../../auth/AuthContext';

export function RunsPage() {
  const { hasPermission } = useAuth();
  const { showError, showSuccess } = useToast();
  const [runs, setRuns] = useState<ConfigRun[]>([]);
  const [configs, setConfigs] = useState<string[]>([]);
  const [configName, setConfigName] = useState('');
  const [runName, setRunName] = useState('');
  const [search, setSearch] = useState('');
  const [detail, setDetail] = useState<ConfigRun | null>(null);

  const load = useCallback(async () => {
    try {
      const map = await runsList();
      setRuns(
        Object.entries(map)
          .map(([id, r]) => ({ ...r, id: Number(id) }))
          .sort((a, b) => a.id - b.id),
      );
      if (hasPermission('config:view')) {
        const names = await configsList();
        setConfigs(names);
        if (!configName && names[0]) setConfigName(names[0]);
      }
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Ошибка загрузки запусков');
    }
  }, [configName, hasPermission, showError]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = runs.filter((r) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (
      String(r.id).includes(q) ||
      (r.name ?? '').toLowerCase().includes(q) ||
      (r.config_path ?? '').toLowerCase().includes(q) ||
      (r.state ?? '').toLowerCase().includes(q)
    );
  });

  return (
    <section className="panel active">
      {hasPermission('runtime:control') ? (
        <div className="card create-card">
          <h2>Новый запуск</h2>
          <div className="form-row run-form-main">
            <select value={configName} onChange={(e) => setConfigName(e.target.value)}>
              {configs.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            <input placeholder="Имя запуска" value={runName} onChange={(e) => setRunName(e.target.value)} />
            <Button
              variant="primary"
              onClick={() => {
                void (async () => {
                  try {
                    await runCreate({ config_name: configName, name: runName || undefined });
                    showSuccess('Запуск создан');
                    setRunName('');
                    await load();
                  } catch (e) {
                    showError(e instanceof ApiError ? e.message : 'Не удалось создать');
                  }
                })();
              }}
            >
              Создать
            </Button>
          </div>
        </div>
      ) : null}
      <div className="card runs-card">
        <h2>Список запусков</h2>
        <div className="toolbar">
          <input className="search-input" placeholder="Поиск…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <Button variant="outline" onClick={() => void load()}>
            Обновить
          </Button>
        </div>
        <ul className="runs-list">
          {filtered.map((r) => (
            <li key={r.id} className="run-item">
              <div className="run-info">
                <span className="run-name">{r.name ?? `Запуск ${r.id}`}</span>
                <span className="run-id">#{r.id}</span>
                <Badge state={r.state}>{r.state}</Badge>
                <span className="run-config">{r.config_path}</span>
              </div>
              <div className="run-actions">
                <Button size="sm" variant="outline" onClick={() => setDetail(r)}>
                  Просмотр
                </Button>
                {r.state === 'running' ? (
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() =>
                      void runStop(r.id)
                        .then(() => {
                          showSuccess('Остановлен');
                          return load();
                        })
                        .catch((e) => showError(e.message))
                    }
                  >
                    Стоп
                  </Button>
                ) : (
                  <>
                    <Button
                      size="sm"
                      variant="success"
                      onClick={() =>
                        void runStart(r.id)
                          .then(() => {
                            showSuccess('Запущен');
                            return load();
                          })
                          .catch((e) => showError(e.message))
                      }
                    >
                      Старт
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        void runDelete(r.id)
                          .then(() => {
                            showSuccess('Удалён');
                            return load();
                          })
                          .catch((e) => showError(e.message))
                      }
                    >
                      Удалить
                    </Button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>
      <Modal open={Boolean(detail)} title="Подробности запуска" onClose={() => setDetail(null)}>
        {detail ? (
          <>
            <p>
              <strong>ID</strong> {detail.id}
            </p>
            <p>
              <strong>Имя</strong> {detail.name ?? '—'}
            </p>
            <p>
              <strong>Статус</strong> {detail.state}
            </p>
            <p>
              <strong>Конфиг</strong> {detail.config_path}
            </p>
            <p>
              <strong>PID</strong> {detail.pid ?? '—'}
            </p>
            {detail.error ? <p className="run-error">{detail.error}</p> : null}
          </>
        ) : null}
      </Modal>
    </section>
  );
}
