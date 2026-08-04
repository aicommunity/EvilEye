import { Link } from 'react-router-dom';
import { EventsPage } from './EventsPage';
import { AuthProvider } from '../../auth/AuthContext';
import { ToastProvider } from '../../components/ui/Toast';

export function MobileEventsPage() {
  return (
    <AuthProvider>
      <ToastProvider>
        <div className="mobile-shell">
          <header className="mobile-header">
            <strong>EvilEye</strong>
            <nav>
              <Link to="/m/live">Live</Link> · <Link to="/m/events">Events</Link> · <Link to="/events">Desktop</Link>
            </nav>
          </header>
          <EventsPage />
        </div>
      </ToastProvider>
    </AuthProvider>
  );
}
