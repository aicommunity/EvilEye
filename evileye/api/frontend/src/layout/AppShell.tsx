import { NavLink, Outlet } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { authApi, systemApi } from '../api';
import { useAuth } from '../auth/AuthContext';
import { Button } from '../components/ui';
import { useToast } from '../components/ui/Toast';
import { useI18n } from '../i18n';
import { AuthModal } from './AuthModal';
import { ForcePasswordGate } from './ForcePasswordGate';

const NAV: Array<{ to: string; labelKey: string; permission?: string }> = [
  { to: '/live', labelKey: 'nav.live', permission: 'live:view' },
  { to: '/events', labelKey: 'nav.events', permission: 'journal:view' },
  { to: '/playback', labelKey: 'nav.playback', permission: 'journal:view' },
  { to: '/configure', labelKey: 'nav.configure', permission: 'config:view' },
  { to: '/admin/runs', labelKey: 'nav.runs', permission: 'runtime:view' },
  { to: '/admin/configs', labelKey: 'nav.configs', permission: 'config:view' },
  { to: '/admin/logs', labelKey: 'nav.logs', permission: 'logs:view' },
  { to: '/admin/users', labelKey: 'nav.users', permission: 'users:manage' },
  { to: '/admin/bans', labelKey: 'nav.bans', permission: 'bans:manage' },
];

export function AppShell() {
  const { loading, authEnabled, user, hasPermission, logout, refresh } = useAuth();
  const { t, lang, setLang } = useI18n();
  const { showError, showSuccess } = useToast();
  const [version, setVersion] = useState('—');
  const [pwOpen, setPwOpen] = useState(false);
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [newPw2, setNewPw2] = useState('');
  const [pwSaving, setPwSaving] = useState(false);
  const needLogin = !loading && authEnabled && !user;

  useEffect(() => {
    void systemApi.version().then((v) => setVersion(`EvilEye ${v.evileye}`)).catch(() => setVersion('—'));
  }, []);

  const onChangePassword = async () => {
    if (newPw.length < 8) {
      showError(t('users.newPassword') + ' (≥10)');
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
      setPwOpen(false);
      setCurrentPw('');
      setNewPw('');
      setNewPw2('');
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    } finally {
      setPwSaving(false);
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h1 className="logo">EvilEye</h1>
          <p className="tagline">{t('shell.tagline')}</p>
        </div>
        <nav className="sidebar-nav">
          {NAV.filter((item) => !item.permission || hasPermission(item.permission)).map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
              {t(item.labelKey)}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <label className="lang-switch">
            <span className="hint">{t('common.language')}</span>
            <select value={lang} onChange={(e) => setLang(e.target.value === 'en' ? 'en' : 'ru')}>
              <option value="ru">RU</option>
              <option value="en">EN</option>
            </select>
          </label>
          {authEnabled && user ? (
            <div className="auth-status">
              <span className="auth-user-label">
                {user.username} ({user.role})
              </span>
              <Button size="sm" variant="outline" onClick={() => setPwOpen(true)}>
                {t('users.changePassword')}
              </Button>
              <Button size="sm" variant="outline" onClick={() => void logout()}>
                {t('shell.logout')}
              </Button>
            </div>
          ) : null}
          <span className="footer-version">{version}</span>
        </div>
      </aside>
      <main className="app-main">
        {loading ? <p className="hint">{t('shell.loading')}</p> : needLogin ? null : <Outlet />}
      </main>
      <AuthModal open={needLogin} />
      <ForcePasswordGate />
      {pwOpen ? (
        <div className="pw-modal-backdrop" onClick={() => !pwSaving && setPwOpen(false)}>
          <div className="change-password-modal" onClick={(e) => e.stopPropagation()}>
            <h3>{t('users.changePassword')}</h3>
            <label>
              <span>{t('users.currentPassword')}</span>
              <input
                type="password"
                value={currentPw}
                onChange={(e) => setCurrentPw(e.target.value)}
                autoComplete="current-password"
              />
            </label>
            <label>
              <span>{t('users.newPassword')}</span>
              <input
                type="password"
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
                minLength={8}
                autoComplete="new-password"
              />
            </label>
            <label>
              <span>{t('users.confirmPassword')}</span>
              <input
                type="password"
                value={newPw2}
                onChange={(e) => setNewPw2(e.target.value)}
                minLength={8}
                autoComplete="new-password"
              />
            </label>
            <div className="modal-actions">
              <Button variant="outline" disabled={pwSaving} onClick={() => setPwOpen(false)}>
                {t('live.stream.close')}
              </Button>
              <Button disabled={pwSaving || !currentPw || newPw.length < 8} onClick={() => void onChangePassword()}>
                {t('users.savePassword')}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
