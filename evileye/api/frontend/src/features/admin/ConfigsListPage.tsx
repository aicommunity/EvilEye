import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { configsList, configGet, configCreate, configUpdate, configDelete, ApiError } from '../../api';
import { Button, Modal } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useAuth } from '../../auth/AuthContext';

export function ConfigsListPage() {
  const { hasPermission } = useAuth();
  const { showError, showSuccess } = useToast();
  const [names, setNames] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState<{ mode: 'view' | 'edit' | 'create'; name?: string } | null>(null);
  const [nameInput, setNameInput] = useState('');
  const [body, setBody] = useState('{}');

  const load = useCallback(async () => {
    try {
      setNames(await configsList());
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Ошибка');
    }
  }, [showError]);

  useEffect(() => {
    void load();
  }, [load]);

  const open = async (mode: 'view' | 'edit' | 'create', name?: string) => {
    setModal({ mode, name });
    if (mode === 'create') {
      setNameInput('');
      setBody('{}');
      return;
    }
    setNameInput(name ?? '');
    try {
      const data = await configGet(name!);
      setBody(JSON.stringify(data, null, 2));
    } catch (e) {
      showError(e instanceof ApiError ? e.message : 'Не удалось загрузить');
    }
  };

  const filtered = names.filter((n) => !search || n.toLowerCase().includes(search.toLowerCase()));

  return (
    <section className="panel active">
      <div className="card">
        <h2>Настройки</h2>
        <p className="hint">JSON-конфиги. Для форм и ROI/Zone — раздел Configure.</p>
        <div className="toolbar">
          <input className="search-input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Поиск…" />
          {hasPermission('config:edit') ? (
            <Button variant="primary" onClick={() => void open('create')}>
              Создать
            </Button>
          ) : null}
          <Link className="btn btn-outline" to="/configure">
            Config Studio
          </Link>
        </div>
        <ul className="configs-list">
          {filtered.map((n) => (
            <li key={n} className="config-item">
              <span className="config-name">{n}</span>
              <div className="config-actions">
                <Button size="sm" variant="outline" onClick={() => void open('view', n)}>
                  Просмотр
                </Button>
                {hasPermission('config:edit') ? (
                  <>
                    <Button size="sm" variant="outline" onClick={() => void open('edit', n)}>
                      Изменить
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() =>
                        void configDelete(n)
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
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      </div>
      <Modal
        open={Boolean(modal)}
        title={modal?.mode === 'create' ? 'Новый конфиг' : `${modal?.mode}: ${modal?.name}`}
        onClose={() => setModal(null)}
        footer={
          modal?.mode !== 'view' ? (
            <Button
              variant="primary"
              onClick={() => {
                void (async () => {
                  try {
                    const parsed = JSON.parse(body || '{}');
                    if (modal?.mode === 'create') {
                      const name = nameInput.endsWith('.json') ? nameInput : `${nameInput}.json`;
                      await configCreate(name, parsed);
                    } else if (modal?.name) {
                      await configUpdate(modal.name, parsed);
                    }
                    showSuccess('Сохранено');
                    setModal(null);
                    await load();
                  } catch (e) {
                    showError(e instanceof Error ? e.message : 'Ошибка сохранения');
                  }
                })();
              }}
            >
              Сохранить
            </Button>
          ) : null
        }
      >
        {modal?.mode === 'create' ? (
          <>
            <label>Имя файла</label>
            <input value={nameInput} onChange={(e) => setNameInput(e.target.value)} />
          </>
        ) : null}
        <label>JSON</label>
        <textarea rows={14} value={body} readOnly={modal?.mode === 'view'} onChange={(e) => setBody(e.target.value)} />
      </Modal>
    </section>
  );
}
