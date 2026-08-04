import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Button } from '../components/ui';
import { useToast } from '../components/ui/Toast';
import { ApiError } from '../api';
import { useI18n } from '../i18n';

export function AuthModal({ open }: { open: boolean }) {
  const { login, register } = useAuth();
  const { showError, showSuccess } = useToast();
  const { t } = useI18n();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [password2, setPassword2] = useState('');
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const handleLogin = async () => {
    if (!username.trim() || !password) {
      showError(t('auth.needCreds'));
      return;
    }
    setBusy(true);
    try {
      await login(username.trim(), password);
      showSuccess(t('auth.success'));
    } catch (e) {
      showError(e instanceof ApiError ? e.message : t('auth.loginFail'));
    } finally {
      setBusy(false);
    }
  };

  const handleRegister = async () => {
    if (!email.trim() || !password) {
      showError(t('auth.needEmail'));
      return;
    }
    if (password !== password2) {
      showError(t('auth.mismatch'));
      return;
    }
    setBusy(true);
    try {
      const msg = await register(email.trim(), password);
      showSuccess(msg);
      setMode('login');
    } catch (e) {
      showError(e instanceof ApiError ? e.message : t('auth.registerFail'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal open" role="dialog" aria-modal="true">
      <div className="modal-backdrop" />
      <div className="modal-content auth-modal-content">
        <div className="modal-header">
          <h2>{t('auth.title')}</h2>
        </div>
        <div className="modal-body">
          <div className="auth-tabs">
            <Button size="sm" variant={mode === 'login' ? 'primary' : 'outline'} onClick={() => setMode('login')}>
              {t('auth.login')}
            </Button>
            <Button size="sm" variant={mode === 'register' ? 'primary' : 'outline'} onClick={() => setMode('register')}>
              {t('auth.register')}
            </Button>
          </div>
          {mode === 'login' ? (
            <>
              <p className="hint">{t('auth.hintLogin')}</p>
              <label>{t('auth.username')}</label>
              <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
              <label>{t('auth.password')}</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void handleLogin();
                }}
              />
              <div className="modal-footer auth-modal-footer">
                <Button variant="primary" disabled={busy} onClick={() => void handleLogin()}>
                  {t('auth.login')}
                </Button>
              </div>
            </>
          ) : (
            <>
              <p className="hint">{t('auth.register')}</p>
              <label>{t('auth.email')}</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              <label>{t('auth.password')}</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
              <label>{t('auth.password2')}</label>
              <input type="password" value={password2} onChange={(e) => setPassword2(e.target.value)} />
              <div className="modal-footer auth-modal-footer">
                <Button variant="primary" disabled={busy} onClick={() => void handleRegister()}>
                  {t('auth.register')}
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
