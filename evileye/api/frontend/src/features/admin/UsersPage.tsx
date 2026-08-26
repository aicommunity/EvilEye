import { useCallback, useEffect, useState } from 'react';
import { usersApi, type CameraCatalogItem, type UserRecord } from '../../api';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n } from '../../i18n';

const MIN_PASSWORD_LEN = 8;

function generatePassword(length = 14): string {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@$%';
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join('');
}

export function UsersPage() {
  const { showError, showSuccess } = useToast();
  const { t } = useI18n();
  const [items, setItems] = useState<UserRecord[]>([]);
  const [catalog, setCatalog] = useState<CameraCatalogItem[]>([]);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showCreatePw, setShowCreatePw] = useState(false);
  const [role, setRole] = useState<'user' | 'admin'>('user');
  const [creating, setCreating] = useState(false);
  const [resetPw, setResetPw] = useState<Record<string, string>>({});
  const [showResetPw, setShowResetPw] = useState<Record<string, boolean>>({});
  const [savingPw, setSavingPw] = useState<Record<string, boolean>>({});
  const [draftCams, setDraftCams] = useState<Record<string, string[]>>({});
  const [savingCams, setSavingCams] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    try {
      const [data, cams] = await Promise.all([usersApi.list(), usersApi.cameraCatalog()]);
      setItems(data.items ?? []);
      setCatalog(cams.items ?? []);
      const next: Record<string, string[]> = {};
      for (const u of data.items ?? []) {
        next[u.id || u.username] = [...(u.allowed_cameras ?? [])];
      }
      setDraftCams(next);
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    }
  }, [showError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onCreate = async () => {
    if (password.length < MIN_PASSWORD_LEN) {
      showError(t('users.passwordTooShort'));
      return;
    }
    setCreating(true);
    try {
      await usersApi.create({ email: email.trim(), password, role });
      showSuccess(t('users.created'));
      setEmail('');
      setPassword('');
      setRole('user');
      setShowCreatePw(false);
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

  const sourceLabel = (value: string) => {
    const key = `users.source.${value}`;
    const translated = t(key);
    return translated === key ? value : translated;
  };

  const patchUser = async (id: string, body: Parameters<typeof usersApi.patch>[1], okMsg: string) => {
    try {
      await usersApi.patch(id, body);
      showSuccess(okMsg);
      await load();
      return true;
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
      return false;
    }
  };

  const saveResetPassword = async (id: string, raw: string) => {
    const pw = raw.trim();
    if (pw.length < MIN_PASSWORD_LEN) {
      showError(t('users.passwordTooShort'));
      return;
    }
    setSavingPw((prev) => ({ ...prev, [id]: true }));
    try {
      const ok = await patchUser(id, { password: pw }, t('users.passwordUpdated'));
      if (ok) {
        setResetPw((prev) => ({ ...prev, [id]: '' }));
        setShowResetPw((prev) => ({ ...prev, [id]: false }));
      }
    } finally {
      setSavingPw((prev) => ({ ...prev, [id]: false }));
    }
  };

  const toggleCam = (userId: string, name: string) => {
    setDraftCams((prev) => {
      const cur = new Set(prev[userId] ?? []);
      if (cur.has(name)) cur.delete(name);
      else cur.add(name);
      return { ...prev, [userId]: Array.from(cur) };
    });
  };

  const saveCams = async (id: string) => {
    setSavingCams((prev) => ({ ...prev, [id]: true }));
    try {
      await patchUser(id, { allowed_cameras: draftCams[id] ?? [] }, t('users.camerasUpdated'));
    } finally {
      setSavingCams((prev) => ({ ...prev, [id]: false }));
    }
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
                <div className="users-pw-field">
                  <input
                    className="search-input"
                    type={showCreatePw ? 'text' : 'password'}
                    required
                    minLength={MIN_PASSWORD_LEN}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                  />
                  <button
                    type="button"
                    className="users-pw-toggle"
                    onClick={() => setShowCreatePw((v) => !v)}
                    aria-label={showCreatePw ? t('users.hidePassword') : t('users.showPassword')}
                    title={showCreatePw ? t('users.hidePassword') : t('users.showPassword')}
                  >
                    {showCreatePw ? t('users.hidePassword') : t('users.showPassword')}
                  </button>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setPassword(generatePassword());
                    setShowCreatePw(true);
                  }}
                >
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
              <Button type="submit" disabled={creating || !email.trim() || password.length < MIN_PASSWORD_LEN}>
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
                  <th>{t('users.identity')}</th>
                  <th>{t('users.sourceHeader')}</th>
                  <th>{t('users.roleHeader')}</th>
                  <th>{t('users.statusHeader')}</th>
                  <th>{t('users.cameras')}</th>
                  <th>{t('users.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((u) => {
                  const id = u.id || u.username;
                  const canApprove = u.source === 'store' && u.status === 'pending';
                  const isActive = !u.disabled && u.status === 'approved';
                  const pwVisible = Boolean(showResetPw[id]);
                  const pwValue = resetPw[id] ?? '';
                  const pwBusy = Boolean(savingPw[id]);
                  const isAdmin = u.role === 'admin';
                  const selected = draftCams[id] ?? [];
                  return (
                    <tr key={`${u.source}:${id}`}>
                      <td>{u.username}</td>
                      <td>{sourceLabel(u.source)}</td>
                      <td>
                        {isActive || u.source === 'credentials' ? (
                          <select
                            className="search-input"
                            value={u.role === 'admin' ? 'admin' : 'user'}
                            onChange={(e) =>
                              void patchUser(
                                id,
                                { role: e.target.value === 'admin' ? 'admin' : 'user' },
                                t('users.roleUpdated'),
                              )
                            }
                          >
                            <option value="user">{roleLabel('user')}</option>
                            <option value="admin">{roleLabel('admin')}</option>
                          </select>
                        ) : (
                          roleLabel(u.role)
                        )}
                      </td>
                      <td>{statusLabel(u.status)}</td>
                      <td>
                        {isAdmin ? (
                          <span className="hint">{t('users.allCamerasAdmin')}</span>
                        ) : !catalog.length ? (
                          <span className="hint">{t('users.camerasHint')}</span>
                        ) : (
                          <div className="users-camera-acl">
                            {catalog.map((c) => (
                              <label key={c.source_name} className="checkbox-label">
                                <input
                                  type="checkbox"
                                  checked={selected.includes(c.source_name)}
                                  onChange={() => toggleCam(id, c.source_name)}
                                />
                                <span>{c.source_name}</span>
                              </label>
                            ))}
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={Boolean(savingCams[id])}
                              onClick={() => void saveCams(id)}
                            >
                              {t('users.saveCameras')}
                            </Button>
                          </div>
                        )}
                      </td>
                      <td>
                        <div className="users-row-actions">
                          {canApprove ? (
                            <div className="users-row-actions-btns">
                              <Button
                                size="sm"
                                variant="success"
                                onClick={() =>
                                  void usersApi.approve(u.email || id).then(() => {
                                    showSuccess(t('users.approved'));
                                    return load();
                                  })
                                }
                              >
                                {t('users.approve')}
                              </Button>
                              <Button
                                size="sm"
                                variant="danger"
                                onClick={() =>
                                  void usersApi.reject(u.email || id).then(() => {
                                    showSuccess(t('users.rejected'));
                                    return load();
                                  })
                                }
                              >
                                {t('users.reject')}
                              </Button>
                            </div>
                          ) : (
                            <>
                              <form
                                className="users-reset-pw"
                                onSubmit={(e) => {
                                  e.preventDefault();
                                  const form = e.currentTarget;
                                  const input = form.elements.namedItem('new-password') as HTMLInputElement | null;
                                  const raw = input?.value ?? pwValue;
                                  void saveResetPassword(id, raw);
                                }}
                              >
                                <div className="users-pw-field">
                                  <input
                                    className="search-input users-reset-pw-input"
                                    name="new-password"
                                    type={pwVisible ? 'text' : 'password'}
                                    placeholder={t('users.resetPassword')}
                                    minLength={MIN_PASSWORD_LEN}
                                    value={pwValue}
                                    onChange={(e) => setResetPw((prev) => ({ ...prev, [id]: e.target.value }))}
                                    autoComplete="new-password"
                                  />
                                  <button
                                    type="button"
                                    className="users-pw-toggle"
                                    onClick={() =>
                                      setShowResetPw((prev) => ({ ...prev, [id]: !prev[id] }))
                                    }
                                    aria-label={pwVisible ? t('users.hidePassword') : t('users.showPassword')}
                                    title={pwVisible ? t('users.hidePassword') : t('users.showPassword')}
                                  >
                                    {pwVisible ? t('users.hidePassword') : t('users.showPassword')}
                                  </button>
                                </div>
                                <div className="users-reset-pw-btns">
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="outline"
                                    onClick={() => {
                                      setResetPw((prev) => ({ ...prev, [id]: generatePassword() }));
                                      setShowResetPw((prev) => ({ ...prev, [id]: true }));
                                    }}
                                  >
                                    {t('users.generatePassword')}
                                  </Button>
                                  <Button type="submit" size="sm" disabled={pwBusy}>
                                    {t('users.savePassword')}
                                  </Button>
                                </div>
                              </form>
                              <div className="users-row-actions-btns">
                                {u.disabled || u.status === 'disabled' || u.status === 'rejected' ? (
                                  <Button
                                    size="sm"
                                    variant="success"
                                    onClick={() =>
                                      void patchUser(id, { disabled: false, status: 'approved' }, t('users.enabled'))
                                    }
                                  >
                                    {t('users.enable')}
                                  </Button>
                                ) : (
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => void patchUser(id, { disabled: true }, t('users.disabledMsg'))}
                                  >
                                    {t('users.disable')}
                                  </Button>
                                )}
                                <Button
                                  size="sm"
                                  variant="danger"
                                  onClick={() => {
                                    if (!window.confirm(t('users.deleteConfirm', { name: u.username }))) return;
                                    void usersApi
                                      .remove(id)
                                      .then(() => {
                                        showSuccess(t('users.deleted'));
                                        return load();
                                      })
                                      .catch((e) => showError(e instanceof Error ? e.message : t('common.error')));
                                  }}
                                >
                                  {t('users.delete')}
                                </Button>
                              </div>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </section>
  );
}
