import { useAuth } from '../auth/AuthContext';
import { AuthModal } from './AuthModal';
import { useI18n } from '../i18n';
import type { ReactNode } from 'react';

/** Mobile shell: login gate without desktop sidebar. */
export function MobileAuthGate({ children }: { children: ReactNode }) {
  const { loading, authEnabled, user } = useAuth();
  const { t } = useI18n();
  const needLogin = !loading && authEnabled && !user;

  if (loading) {
    return <p className="hint" style={{ padding: 16 }}>{t('shell.loading')}</p>;
  }
  return (
    <>
      {needLogin ? null : children}
      <AuthModal open={needLogin} />
    </>
  );
}
