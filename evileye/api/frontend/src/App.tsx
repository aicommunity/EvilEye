import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import { RequirePermission } from './auth/RequirePermission';
import { ToastProvider } from './components/ui/Toast';
import { AppShell } from './layout/AppShell';
import { LivePage } from './features/live/LivePage';
import { EventsPage } from './features/journals/EventsPage';
import { PlaybackPage } from './features/playback/PlaybackPage';
import { ConfigurePage } from './features/configure/ConfigurePage';
import { OverviewPage } from './features/admin/OverviewPage';
import { RunsPage } from './features/admin/RunsPage';
import { ConfigsListPage } from './features/admin/ConfigsListPage';
import { LogsPage } from './features/admin/LogsPage';
import { UsersPage } from './features/admin/UsersPage';
import { HistoryPage } from './features/admin/HistoryPage';
import { MobileLivePage } from './features/live/MobileLivePage';
import { MobileEventsPage } from './features/journals/MobileEventsPage';
import './styles/global.css';

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/m/live" element={<MobileLivePage />} />
            <Route path="/m/events" element={<MobileEventsPage />} />
            <Route element={<AppShell />}>
              <Route index element={<Navigate to="/live" replace />} />
              <Route
                path="/live"
                element={
                  <RequirePermission permission="live:view">
                    <LivePage />
                  </RequirePermission>
                }
              />
              <Route
                path="/events"
                element={
                  <RequirePermission permission="journal:view">
                    <EventsPage />
                  </RequirePermission>
                }
              />
              <Route
                path="/playback"
                element={
                  <RequirePermission permission="journal:view">
                    <PlaybackPage />
                  </RequirePermission>
                }
              />
              <Route
                path="/configure/:name?"
                element={
                  <RequirePermission permission="config:view">
                    <ConfigurePage />
                  </RequirePermission>
                }
              />
              <Route
                path="/admin/overview"
                element={
                  <RequirePermission permission="live:view">
                    <OverviewPage />
                  </RequirePermission>
                }
              />
              <Route
                path="/admin/runs"
                element={
                  <RequirePermission permission="runtime:view">
                    <RunsPage />
                  </RequirePermission>
                }
              />
              <Route
                path="/admin/configs"
                element={
                  <RequirePermission permission="config:view">
                    <ConfigsListPage />
                  </RequirePermission>
                }
              />
              <Route
                path="/admin/logs"
                element={
                  <RequirePermission permission="logs:view">
                    <LogsPage />
                  </RequirePermission>
                }
              />
              <Route
                path="/admin/users"
                element={
                  <RequirePermission permission="users:manage">
                    <UsersPage />
                  </RequirePermission>
                }
              />
              <Route
                path="/admin/history"
                element={
                  <RequirePermission permission="history:view">
                    <HistoryPage />
                  </RequirePermission>
                }
              />
            </Route>
            <Route path="*" element={<Navigate to="/live" replace />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </AuthProvider>
  );
}
