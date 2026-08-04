import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { configsList, configGet, configCreate, configUpdate, configDelete, ApiError } from '../../api';
import { Button, Modal } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useAuth } from '../../auth/AuthContext';
import { useI18n } from '../../i18n';

export function ConfigsListPage() {
  const { hasPermission } = useAuth();
  const { showError, showSuccess } = useToast();
  const { t } = useI18n();
  const [names, setNames] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState<{ mode: 'raw' | 'create'; name?: string } | null>(null);
  const [nameInput, setNameInput] = useState('');
  const [body, setBody] = useState('{}');

  const load = useCallback(async () => {
    try {
      setNames(await configsList());
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    }
  }, [showError]);

  useEffect(() => {
    void load();
  }, [load]);

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
          {filtered.map((n) => (
            <li key={n} className="config-item">
              <span className="config-name">{n}</span>
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
          ))}
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
                    const parsed = JSON.parse(body || '{}');
                    if (modal?.mode === 'create') {
                      const name = nameInput.endsWith('.json') ? nameInput : `${nameInput}.json`;
                      await configCreate(name, parsed);
                    } else if (modal?.name) {
                      await configUpdate(modal.name, parsed);
                    }
                    showSuccess(t('configs.saved'));
                    setModal(null);
                    await load();
                  } catch (e) {
                    showError(e instanceof Error ? e.message : t('common.saveFail'));
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
          <>
            <label>{t('configs.fileName')}</label>
            <input value={nameInput} onChange={(e) => setNameInput(e.target.value)} />
          </>
        ) : null}
        <label>{t('common.json')}</label>
        <textarea rows={14} value={body} onChange={(e) => setBody(e.target.value)} />
      </Modal>
    </section>
  );
}
