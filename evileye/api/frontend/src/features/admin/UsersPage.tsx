import { useCallback, useEffect, useState } from 'react';
import { usersApi } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';

export function UsersPage() {
  const { showError, showSuccess } = useToast();
  const [items, setItems] = useState<Array<{ email: string; role: string; status: string }>>([]);

  const load = useCallback(async () => {
    try {
      const data = await usersApi.list();
      setItems(data.items ?? []);
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
          <h2 style={{ margin: 0 }}>Пользователи</h2>
          <Button variant="outline" onClick={() => void load()}>
            Обновить
          </Button>
        </div>
        {!items.length ? (
          <p className="empty">Пользователей пока нет.</p>
        ) : (
          <table className="journal-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Роль</th>
                <th>Статус</th>
                <th>Действия</th>
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
                              showSuccess('Подтверждён');
                              return load();
                            })
                          }
                        >
                          Approve
                        </Button>{' '}
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() =>
                            void usersApi.reject(u.email).then(() => {
                              showSuccess('Отклонён');
                              return load();
                            })
                          }
                        >
                          Reject
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
