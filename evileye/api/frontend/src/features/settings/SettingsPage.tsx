import { useEffect, useMemo, useState } from 'react';
import { authApi, stateApi } from '../../api';
import { useAuth } from '../../auth/AuthContext';
import { Button } from '../../components/ui';
import { useToast } from '../../components/ui/Toast';
import { useI18n, type DateFormat } from '../../i18n';

export function SettingsPage() {
  const { t, lang, setLang, dateFormat, setDateFormat } = useI18n();
  const { authEnabled, user, cameraAccess, allowedCameras, prefs, refresh } = useAuth();
  const { showError, showSuccess } = useToast();

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
          setCameraNames(names);
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

  const canChangePassword = Boolean(authEnabled && user);

  const emptyAllowed = useMemo(
    () => cameraAccess === 'restricted' && !(allowedCameras?.length),
    [cameraAccess, allowedCameras],
  );

  const toggleCam = (name: string) => {
    setAllVisible(false);
    setVisible((prev) => (prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]));
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

  return (
    <section className="panel active">
      <div className="card">
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>{t('settings.title')}</h2>
        </div>
        <p className="hint">{t('settings.hint')}</p>

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
