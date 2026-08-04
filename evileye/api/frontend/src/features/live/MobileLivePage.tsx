import { Link } from 'react-router-dom';
import { AuthProvider } from '../../auth/AuthContext';
import { ToastProvider } from '../../components/ui/Toast';
import { LivePage } from './LivePage';

export function MobileLivePage() {
  return (
    <AuthProvider>
      <ToastProvider>
        <div className="mobile-shell">
          <header className="mobile-header">
            <strong>EvilEye</strong>
            <nav>
              <Link to="/m/live">Live</Link> · <Link to="/m/events">Events</Link> · <Link to="/live">Desktop</Link>
            </nav>
          </header>
          <LivePage />
        </div>
      </ToastProvider>
    </AuthProvider>
  );
}
