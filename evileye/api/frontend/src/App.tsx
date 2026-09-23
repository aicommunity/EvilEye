import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import { RequirePermission } from './auth/RequirePermission';
import { ToastProvider } from './components/ui/Toast';
import { I18nProvider } from './i18n';
import { AppShell } from './layout/AppShell';
import { MobileAuthGate } from './layout/MobileAuthGate';
import './styles/global.css';

const LivePage = lazy(() => import('./features/live/LivePage').then((m) => ({ default: m.LivePage })));
const EventsPage = lazy(() =>
  import('./features/journals/EventsPage').then((m) => ({ default: m.EventsPage })),
);
const PlaybackPage = lazy(() =>
  import('./features/playback/PlaybackPage').then((m) => ({ default: m.PlaybackPage })),
);
const ConfigurePage = lazy(() =>
  import('./features/configure/ConfigurePage').then((m) => ({ default: m.ConfigurePage })),
);
const RunsPage = lazy(() => import('./features/admin/RunsPage').then((m) => ({ default: m.RunsPage })));
const ConfigsListPage = lazy(() =>
  import('./features/admin/ConfigsListPage').then((m) => ({ default: m.ConfigsListPage })),
);
const ConfigFilePage = lazy(() =>
  import('./features/admin/ConfigFilePage').then((m) => ({ default: m.ConfigFilePage })),
);
const LogsPage = lazy(() => import('./features/admin/LogsPage').then((m) => ({ default: m.LogsPage })));
const UsersPage = lazy(() => import('./features/admin/UsersPage').then((m) => ({ default: m.UsersPage })));
const BansPage = lazy(() => import('./features/admin/BansPage').then((m) => ({ default: m.BansPage })));
const SettingsPage = lazy(() =>
  import('./features/settings/SettingsPage').then((m) => ({ default: m.SettingsPage })),
);
const MobileLivePage = lazy(() =>
  import('./features/live/MobileLivePage').then((m) => ({ default: m.MobileLivePage })),
);
const MobileEventsPage = lazy(() =>
  import('./features/journals/MobileEventsPage').then((m) => ({ default: m.MobileEventsPage })),
);

function LazyRoute({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<p className="hint">…</p>}>{children}</Suspense>;
}

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <ToastProvider>
          <BrowserRouter>
            <Routes>
              <Route
                path="/m/live"
                element={
                  <MobileAuthGate>
                    <RequirePermission permission="live:view">
                      <LazyRoute>
                        <MobileLivePage />
                      </LazyRoute>
                    </RequirePermission>
                  </MobileAuthGate>
                }
              />
              <Route
                path="/m/events"
                element={
                  <MobileAuthGate>
                    <RequirePermission permission="journal:view">
                      <LazyRoute>
                        <MobileEventsPage />
                      </LazyRoute>
                    </RequirePermission>
                  </MobileAuthGate>
                }
              />
              <Route element={<AppShell />}>
                <Route index element={<Navigate to="/live" replace />} />
                <Route
                  path="/live"
                  element={
                    <RequirePermission permission="live:view">
                      <LazyRoute>
                        <LivePage />
                      </LazyRoute>
                    </RequirePermission>
                  }
                />
                <Route
                  path="/events"
                  element={
                    <RequirePermission permission="journal:view">
                      <LazyRoute>
                        <EventsPage />
                      </LazyRoute>
                    </RequirePermission>
                  }
                />
                <Route
                  path="/playback"
                  element={
                    <RequirePermission permission="journal:view">
                      <LazyRoute>
                        <PlaybackPage />
                      </LazyRoute>
                    </RequirePermission>
                  }
                />
                <Route
                  path="/configure/:name?"
                  element={
                    <RequirePermission permission="config:view">
                      <LazyRoute>
                        <ConfigurePage />
                      </LazyRoute>
                    </RequirePermission>
                  }
                />
                <Route path="/admin/overview" element={<Navigate to="/live" replace />} />
                <Route
                  path="/admin/runs"
                  element={
                    <RequirePermission permission="runtime:view">
                      <LazyRoute>
                        <RunsPage />
                      </LazyRoute>
                    </RequirePermission>
                  }
                />
                <Route
                  path="/admin/configs"
                  element={
                    <RequirePermission permission="config:view">
                      <LazyRoute>
                        <ConfigsListPage />
                      </LazyRoute>
                    </RequirePermission>
                  }
                />
                <Route
                  path="/admin/configs/:name"
                  element={
                    <RequirePermission permission="config:view">
                      <LazyRoute>
                        <ConfigFilePage />
                      </LazyRoute>
                    </RequirePermission>
                  }
                />
                <Route
                  path="/admin/logs"
                  element={
                    <RequirePermission permission="logs:view">
                      <LazyRoute>
                        <LogsPage />
                      </LazyRoute>
                    </RequirePermission>
                  }
                />
                <Route
                  path="/admin/users"
                  element={
                    <RequirePermission permission="users:manage">
                      <LazyRoute>
                        <UsersPage />
                      </LazyRoute>
                    </RequirePermission>
                  }
                />
                <Route
                  path="/admin/bans"
                  element={
                    <RequirePermission permission="bans:manage">
                      <LazyRoute>
                        <BansPage />
                      </LazyRoute>
                    </RequirePermission>
                  }
                />
                <Route
                  path="/settings"
                  element={
                    <LazyRoute>
                      <SettingsPage />
                    </LazyRoute>
                  }
                />
                <Route path="/admin/history" element={<Navigate to="/admin/runs" replace />} />
              </Route>
              <Route path="*" element={<Navigate to="/live" replace />} />
            </Routes>
          </BrowserRouter>
        </ToastProvider>
      </AuthProvider>
    </I18nProvider>
  );
}
