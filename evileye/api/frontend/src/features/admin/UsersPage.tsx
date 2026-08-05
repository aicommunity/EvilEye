import { useCallback, useEffect, useState } from 'react';
import { usersApi } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';

function generatePassword(length = 14): string {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@$%';
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join('');
}

export function UsersPage() {
  const { showError, showSuccess } = useToast();
  const { t } = useI18n();
  const [items, setItems] = useState<Array<{ email: string; role: string; status: string }>>([]);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<'user' | 'admin'>('user');
  const [creating, setCreating] = useState(false);

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

  const onCreate = async () => {
    setCreating(true);
    try {
      await usersApi.create({ email: email.trim(), password, role });
      showSuccess(t('users.created'));
      setEmail('');
      setPassword('');
      setRole('user');
      await load();
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    } finally {
      setCreating(false);
    }
  };

  const roleLabel = (value: string) => {
    const key = `users.role.${value}`;
    const translated = t(key);
    return translated === key ? value : translated;
  };

  const statusLabel = (value: string) => {
    const key = `users.status.${value}`;
    const translated = t(key);
    return translated === key ? value : translated;
  };

  return (
    <section className="panel active">
      <div className="card">
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>{t('users.title')}</h2>
          <Button variant="outline" onClick={() => void load()}>
            {t('users.refresh')}
          </Button>
        </div>

        <div className="users-create">
          <h3 className="users-create-title">{t('users.createSection')}</h3>
          <p className="hint users-create-hint">{t('users.createHint')}</p>
          <form
            className="users-create-form"
            onSubmit={(e) => {
              e.preventDefault();
              void onCreate();
            }}
          >
            <label className="users-create-field">
              <span>{t('users.email')}</span>
              <input
                className="search-input"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="off"
              />
            </label>
            <label className="users-create-field users-create-field--password">
              <span>{t('users.password')}</span>
              <div className="users-create-password-row">
                <input
                  className="search-input"
                  type="text"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                />
                <Button type="button" size="sm" variant="outline" onClick={() => setPassword(generatePassword())}>
                  {t('users.generatePassword')}
                </Button>
              </div>
            </label>
            <label className="users-create-field">
              <span>{t('users.roleHeader')}</span>
              <select
                className="search-input"
                value={role}
                onChange={(e) => setRole(e.target.value === 'admin' ? 'admin' : 'user')}
              >
                <option value="user">{t('users.role.user')}</option>
                <option value="admin">{t('users.role.admin')}</option>
              </select>
            </label>
            <div className="users-create-field users-create-actions">
              <span className="users-create-label-spacer" aria-hidden>
                &nbsp;
              </span>
              <Button type="submit" disabled={creating || !email.trim() || password.length < 10}>
                {t('users.create')}
              </Button>
            </div>
          </form>
        </div>

        <div className="users-list">
          <h3 className="users-list-title">{t('users.listSection')}</h3>
          {!items.length ? (
            <p className="empty">{t('users.empty')}</p>
          ) : (
            <table className="journal-table">
              <thead>
                <tr>
                  <th>{t('users.email')}</th>
                  <th>{t('users.roleHeader')}</th>
                  <th>{t('users.statusHeader')}</th>
                  <th>{t('users.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((u) => (
                  <tr key={u.email}>
                    <td>{u.email}</td>
                    <td>{roleLabel(u.role)}</td>
                    <td>{statusLabel(u.status)}</td>
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
      </div>
    </section>
  );
}
