import { NavLink, Outlet } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { systemApi } from '../api';
import { useAuth } from '../auth/AuthContext';
import { Button } from '../components/ui';
import { useI18n } from '../i18n';
import { AuthModal } from './AuthModal';
import { ForcePasswordGate } from './ForcePasswordGate';

const NAV: Array<{ to: string; labelKey: string; group: 'monitoring' | 'configuration' | 'administration'; permission?: string; adminOnly?: boolean }> = [
  { to: '/live', labelKey: 'nav.live', group: 'monitoring', permission: 'live:view' },
  { to: '/events', labelKey: 'nav.events', group: 'monitoring', permission: 'journal:view' },
  { to: '/playback', labelKey: 'nav.playback', group: 'monitoring', permission: 'journal:view' },
  { to: '/configure', labelKey: 'nav.configure', group: 'configuration', permission: 'config:view' },
  { to: '/admin/runs', labelKey: 'nav.runs', group: 'configuration', permission: 'runtime:view' },
  { to: '/admin/configs', labelKey: 'nav.configs', group: 'configuration', permission: 'config:view' },
  { to: '/settings', labelKey: 'nav.settings', group: 'configuration' },
  { to: '/admin/users', labelKey: 'nav.users', group: 'administration', permission: 'users:manage' },
  { to: '/admin/bans', labelKey: 'nav.bans', group: 'administration', permission: 'bans:manage' },
  { to: '/admin/extensions', labelKey: 'nav.extensions', group: 'administration', permission: 'system:admin', adminOnly: true },
];

export function AppShell() {
  const { loading, authEnabled, user, hasPermission, logout } = useAuth();
  const { t } = useI18n();
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
          {(['monitoring', 'configuration', 'administration'] as const).map((group) => {
            const items = NAV.filter((item) => item.group === group
              && (!item.adminOnly || (authEnabled && user?.role === 'admin'))
              && (!item.permission || hasPermission(item.permission)));
            if (!items.length) return null;
            return <section className="sidebar-nav-group" key={group} aria-label={t(`nav.group.${group}`)}>
              <h2>{t(`nav.group.${group}`)}</h2>
              {items.map((item) => <NavLink key={item.to} to={item.to} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                {t(item.labelKey)}
              </NavLink>)}
            </section>;
          })}
        </nav>
        <div className="sidebar-footer">
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
      <ForcePasswordGate />
    </div>
  );
}
