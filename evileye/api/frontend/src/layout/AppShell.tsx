import { NavLink, Outlet } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { systemApi } from '../api';
import { useAuth } from '../auth/AuthContext';
import { Button } from '../components/ui';
import { useI18n } from '../i18n';
import { AuthModal } from './AuthModal';

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
  const { loading, authEnabled, user, hasPermission, logout } = useAuth();
  const { t, lang, setLang } = useI18n();
  const [version, setVersion] = useState('—');
  const needLogin = !loading && authEnabled && !user;

  useEffect(() => {
    void systemApi.version().then((v) => setVersion(`EvilEye ${v.evileye}`)).catch(() => setVersion('—'));
  }, []);

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
    </div>
  );
}
