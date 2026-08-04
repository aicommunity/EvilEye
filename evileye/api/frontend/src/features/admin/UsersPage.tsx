import { useCallback, useEffect, useState } from 'react';
import { usersApi } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';

export function UsersPage() {
  const { showError, showSuccess } = useToast();
  const { t } = useI18n();
  const [items, setItems] = useState<Array<{ email: string; role: string; status: string }>>([]);

  const load = useCallback(async () => {
    try {
      const data = await usersApi.list();
      setItems(data.items ?? []);
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    }
  }, [showError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="panel active">
      <div className="card">
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>{t('users.title')}</h2>
          <Button variant="outline" onClick={() => void load()}>
            {t('users.refresh')}
          </Button>
        </div>
        {!items.length ? (
          <p className="empty">{t('users.empty')}</p>
        ) : (
          <table className="journal-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>{t('users.role')}</th>
                <th>{t('users.status')}</th>
                <th>{t('users.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((u) => (
                <tr key={u.email}>
                  <td>{u.email}</td>
                  <td>{u.role}</td>
                  <td>{u.status}</td>
                  <td>
                    {u.status === 'pending' ? (
                      <>
                        <Button
                          size="sm"
                          variant="success"
                          onClick={() =>
                            void usersApi.approve(u.email).then(() => {
                              showSuccess(t('users.approved'));
                              return load();
                            })
                          }
                        >
                          {t('users.approve')}
                        </Button>{' '}
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() =>
                            void usersApi.reject(u.email).then(() => {
                              showSuccess(t('users.rejected'));
                              return load();
                            })
                          }
                        >
                          {t('users.reject')}
                        </Button>
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
