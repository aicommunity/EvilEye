import { NavLink, Outlet } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { systemApi } from '../api';
import { useAuth } from '../auth/AuthContext';
import { Button } from '../components/ui';
import { AuthModal } from './AuthModal';

const NAV: Array<{ to: string; label: string; permission?: string }> = [
  { to: '/live', label: 'Live', permission: 'live:view' },
  { to: '/events', label: 'События', permission: 'journal:view' },
  { to: '/playback', label: 'Playback', permission: 'journal:view' },
  { to: '/configure', label: 'Configure', permission: 'config:view' },
  { to: '/admin/overview', label: 'Обзор', permission: 'live:view' },
  { to: '/admin/runs', label: 'Запуски', permission: 'runtime:view' },
  { to: '/admin/configs', label: 'Конфиги', permission: 'config:view' },
  { to: '/admin/logs', label: 'Логи', permission: 'logs:view' },
  { to: '/admin/history', label: 'История', permission: 'history:view' },
  { to: '/admin/users', label: 'Пользователи', permission: 'users:manage' },
];

export function AppShell() {
  const { loading, authEnabled, user, hasPermission, logout } = useAuth();
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
          <p className="tagline">Операционная консоль</p>
        </div>
        <nav className="sidebar-nav">
          {NAV.filter((item) => !item.permission || hasPermission(item.permission)).map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          {authEnabled && user ? (
            <div className="auth-status">
              <span className="auth-user-label">
                {user.username} ({user.role})
              </span>
              <Button size="sm" variant="outline" onClick={() => void logout()}>
                Выйти
              </Button>
            </div>
          ) : null}
          <span className="footer-version">{version}</span>
        </div>
      </aside>
      <main className="app-main">
        {loading ? <p className="hint">Загрузка…</p> : needLogin ? null : <Outlet />}
      </main>
      <AuthModal open={needLogin} />
    </div>
  );
}
