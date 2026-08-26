import { Link } from 'react-router-dom';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { authApi, stateApi, usersApi, type CameraCatalogItem, type UserRecord } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n, type DateFormat } from '../../i18n';
import { CameraAclEditor } from '../admin/CameraAclEditor';

export function SettingsPage() {
  const { t, lang, setLang, dateFormat, setDateFormat } = useI18n();
  const {
    authEnabled,
    user,
    cameraAccess,
    allowedCameras,
    prefs,
    refresh,
    hasPermission,
  } = useAuth();
  const { showError, showSuccess } = useToast();
  const canManageUsers = hasPermission('users:manage');

  const [uiLang, setUiLang] = useState<'ru' | 'en'>(lang);
  const [uiDate, setUiDate] = useState<DateFormat>(dateFormat);
  const [cameraNames, setCameraNames] = useState<string[]>([]);
  const [visible, setVisible] = useState<string[]>([]);
  const [allVisible, setAllVisible] = useState(true);
  const [savingPrefs, setSavingPrefs] = useState(false);

  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [newPw2, setNewPw2] = useState('');
  const [pwSaving, setPwSaving] = useState(false);

  const [aclUsers, setAclUsers] = useState<UserRecord[]>([]);
  const [aclCatalog, setAclCatalog] = useState<CameraCatalogItem[]>([]);
  const [aclDraft, setAclDraft] = useState<Record<string, string[]>>({});
  const [aclSaving, setAclSaving] = useState<Record<string, boolean>>({});
  const [aclLoading, setAclLoading] = useState(false);

  useEffect(() => {
    setUiLang(lang);
    setUiDate(dateFormat);
  }, [lang, dateFormat]);

  useEffect(() => {
    if (prefs?.lang === 'ru' || prefs?.lang === 'en') setLang(prefs.lang);
    if (
      prefs?.date_format === 'DD-MM-YYYY' ||
      prefs?.date_format === 'YYYY-MM-DD' ||
      prefs?.date_format === 'MM-DD-YYYY'
    ) {
      setDateFormat(prefs.date_format);
    }
  }, [prefs, setLang, setDateFormat]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        if (cameraAccess === 'all') {
          const res = await stateApi.cameras('active');
          if (cancelled) return;
          const names = [...new Set((res.items ?? []).map((c) => c.source_name).filter(Boolean))];
          setCameraNames(names.length ? names : [...(allowedCameras ?? [])]);
        } else {
          setCameraNames([...(allowedCameras ?? [])]);
        }
      } catch {
        if (!cancelled) setCameraNames([...(allowedCameras ?? [])]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [cameraAccess, allowedCameras]);

  useEffect(() => {
    if (prefs?.visible_cameras == null) {
      setAllVisible(true);
      setVisible([...cameraNames]);
    } else {
      setAllVisible(false);
      setVisible([...(prefs.visible_cameras ?? [])]);
    }
  }, [prefs, cameraNames]);

  const loadAcl = useCallback(async () => {
    if (!canManageUsers) return;
    setAclLoading(true);
    try {
      const usersRes = await usersApi.list();
      setAclUsers(usersRes.items ?? []);
      const next: Record<string, string[]> = {};
      for (const u of usersRes.items ?? []) {
        next[u.id || u.username] = [...(u.allowed_cameras ?? [])];
      }
      setAclDraft(next);
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
      setAclLoading(false);
      return;
    }
    try {
      const catalogRes = await usersApi.cameraCatalog();
      setAclCatalog(catalogRes.items ?? []);
    } catch {
      setAclCatalog([]);
    } finally {
      setAclLoading(false);
    }
  }, [canManageUsers, showError, t]);

  useEffect(() => {
    void loadAcl();
  }, [loadAcl]);

  const canChangePassword = Boolean(authEnabled && user);

  const emptyAllowed = useMemo(
    () => cameraAccess === 'restricted' && !(allowedCameras?.length),
    [cameraAccess, allowedCameras],
  );

  const toggleCam = (name: string) => {
    setAllVisible(false);
    setVisible((prev) => (prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]));
  };

  const aclSaveGen = useRef<Record<string, number>>({});

  const saveAcl = async (id: string, next: string[]) => {
    const gen = (aclSaveGen.current[id] = (aclSaveGen.current[id] ?? 0) + 1);
    setAclDraft((prev) => ({ ...prev, [id]: next }));
    setAclSaving((prev) => ({ ...prev, [id]: true }));
    try {
      await usersApi.patch(id, { allowed_cameras: next });
      if (aclSaveGen.current[id] !== gen) return;
      setAclUsers((prev) =>
        prev.map((u) => ((u.id || u.username) === id ? { ...u, allowed_cameras: next } : u)),
      );
      showSuccess(t('users.camerasUpdated'));
    } catch (e) {
      if (aclSaveGen.current[id] !== gen) return;
      showError(e instanceof Error ? e.message : t('common.error'));
      await loadAcl();
    } finally {
      if (aclSaveGen.current[id] === gen) {
        setAclSaving((prev) => ({ ...prev, [id]: false }));
      }
    }
  };

  const onSavePrefs = async () => {
    setSavingPrefs(true);
    try {
      setLang(uiLang);
      setDateFormat(uiDate);
      if (authEnabled && user) {
        await authApi.putPrefs({
          lang: uiLang,
          date_format: uiDate,
          visible_cameras: allVisible ? null : visible,
        });
        await refresh();
      }
      showSuccess(t('settings.saved'));
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    } finally {
      setSavingPrefs(false);
    }
  };

  const onChangePassword = async () => {
    if (newPw.length < 8) {
      showError(t('users.newPassword') + ' (≥8)');
      return;
    }
    if (newPw !== newPw2) {
      showError(t('users.passwordMismatch'));
      return;
    }
    setPwSaving(true);
    try {
      await authApi.changePassword({ current_password: currentPw, new_password: newPw });
      showSuccess(t('users.passwordChanged'));
      setCurrentPw('');
      setNewPw('');
      setNewPw2('');
      await refresh();
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    } finally {
      setPwSaving(false);
    }
  };

  const nonAdminUsers = aclUsers.filter((u) => u.role !== 'admin');

  return (
    <section className="panel active">
      <div className="card">
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>{t('settings.title')}</h2>
        </div>
        <p className="hint">{t('settings.hint')}</p>

        {canManageUsers ? (
          <div className="settings-section">
            <h3 className="settings-section-title">{t('settings.adminAclTitle')}</h3>
            <p className="hint">{t('settings.adminAclHint')}</p>
            <p className="hint">
              <Link to="/admin/users">{t('settings.adminAclUsersLink')}</Link>
            </p>
            {aclLoading ? (
              <p className="hint">{t('common.loading')}</p>
            ) : !nonAdminUsers.length ? (
              <p className="empty">{t('settings.adminAclNoUsers')}</p>
            ) : (
              <div className="settings-acl-list">
                {nonAdminUsers.map((u) => {
                  const id = u.id || u.username;
                  const selected = aclDraft[id] ?? [];
                  return (
                    <div key={`${u.source}:${id}`} className="settings-acl-card">
                      <div className="settings-acl-card-head">
                        <strong>{u.username}</strong>
                        <span className="hint">
                          {u.role} · {u.status}
                        </span>
                      </div>
                      <CameraAclEditor
                        selected={selected}
                        catalog={aclCatalog.map((c) => c.source_name)}
                        saving={Boolean(aclSaving[id])}
                        onChange={(next) => void saveAcl(id, next)}
                      />
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : null}

        <div className="settings-section">
          <h3 className="settings-section-title">{t('settings.uiSection')}</h3>
          <div className="settings-form-grid">
            <label className="settings-field">
              <span className="hint">{t('settings.language')}</span>
              <select
                className="search-input"
                value={uiLang}
                onChange={(e) => setUiLang(e.target.value === 'en' ? 'en' : 'ru')}
              >
                <option value="ru">RU</option>
                <option value="en">EN</option>
              </select>
            </label>
            <label className="settings-field">
              <span className="hint">{t('settings.dateFormat')}</span>
              <select
                className="search-input"
                value={uiDate}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === 'DD-MM-YYYY' || v === 'YYYY-MM-DD' || v === 'MM-DD-YYYY') setUiDate(v);
                }}
              >
                <option value="DD-MM-YYYY">DD-MM-YYYY</option>
                <option value="YYYY-MM-DD">YYYY-MM-DD</option>
                <option value="MM-DD-YYYY">MM-DD-YYYY</option>
              </select>
            </label>
          </div>
        </div>

        <div className="settings-section">
          <h3 className="settings-section-title">{t('settings.camerasSection')}</h3>
          <p className="hint">{t('settings.camerasHint')}</p>
          {emptyAllowed ? (
            <p className="empty">{t('settings.noCamerasAllowed')}</p>
          ) : !cameraNames.length ? (
            <p className="empty">{t('settings.noCamerasAllowed')}</p>
          ) : (
            <div className="settings-cameras">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={allVisible}
                  onChange={(e) => {
                    setAllVisible(e.target.checked);
                    if (e.target.checked) setVisible([...cameraNames]);
                  }}
                />
                <span>{t('settings.allVisible')}</span>
              </label>
              {cameraNames.map((name) => (
                <label key={name} className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={allVisible || visible.includes(name)}
                    disabled={allVisible}
                    onChange={() => toggleCam(name)}
                  />
                  <span>{name}</span>
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="form-actions-inline">
          <Button onClick={() => void onSavePrefs()} disabled={savingPrefs}>
            {t('settings.save')}
          </Button>
        </div>

        {canChangePassword ? (
          <div className="settings-section">
            <h3 className="settings-section-title">{t('settings.passwordSection')}</h3>
            <div className="settings-form-grid">
              <label className="settings-field">
                <span className="hint">{t('users.currentPassword')}</span>
                <input
                  className="search-input"
                  type="password"
                  value={currentPw}
                  onChange={(e) => setCurrentPw(e.target.value)}
                  autoComplete="current-password"
                />
              </label>
              <label className="settings-field">
                <span className="hint">{t('users.newPassword')}</span>
                <input
                  className="search-input"
                  type="password"
                  value={newPw}
                  onChange={(e) => setNewPw(e.target.value)}
                  autoComplete="new-password"
                />
              </label>
              <label className="settings-field">
                <span className="hint">{t('users.confirmPassword')}</span>
                <input
                  className="search-input"
                  type="password"
                  value={newPw2}
                  onChange={(e) => setNewPw2(e.target.value)}
                  autoComplete="new-password"
                />
              </label>
            </div>
            <div className="form-actions-inline">
              <Button onClick={() => void onChangePassword()} disabled={pwSaving}>
                {t('users.changePassword')}
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
