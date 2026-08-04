import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Button } from '../components/ui';
import { useToast } from '../components/ui/Toast';
import { ApiError } from '../api';

export function AuthModal({ open }: { open: boolean }) {
  const { login, register } = useAuth();
  const { showError, showSuccess } = useToast();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [password2, setPassword2] = useState('');
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const handleLogin = async () => {
    if (!username.trim() || !password) {
      showError('Введите имя пользователя и пароль');
      return;
    }
    setBusy(true);
    try {
      await login(username.trim(), password);
      showSuccess('Вход выполнен');
    } catch (e) {
      showError(e instanceof ApiError ? e.message : 'Не удалось выполнить вход');
    } finally {
      setBusy(false);
    }
  };

  const handleRegister = async () => {
    if (!email.trim() || !password) {
      showError('Заполните email и пароль');
      return;
    }
    if (password !== password2) {
      showError('Пароли не совпадают');
      return;
    }
    setBusy(true);
    try {
      const msg = await register(email.trim(), password);
      showSuccess(msg);
      setMode('login');
    } catch (e) {
      showError(e instanceof ApiError ? e.message : 'Не удалось зарегистрироваться');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal open" role="dialog" aria-modal="true">
      <div className="modal-backdrop" />
      <div className="modal-content auth-modal-content">
        <div className="modal-header">
          <h2>Вход в веб-интерфейс</h2>
        </div>
        <div className="modal-body">
          <div className="auth-tabs">
            <Button size="sm" variant={mode === 'login' ? 'primary' : 'outline'} onClick={() => setMode('login')}>
              Вход
            </Button>
            <Button size="sm" variant={mode === 'register' ? 'primary' : 'outline'} onClick={() => setMode('register')}>
              Регистрация
            </Button>
          </div>
          {mode === 'login' ? (
            <>
              <p className="hint">Введите имя пользователя или email и пароль.</p>
              <label>Имя пользователя / email</label>
              <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
              <label>Пароль</label>
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
                  Войти
                </Button>
              </div>
            </>
          ) : (
            <>
              <p className="hint">Регистрация по email. После отправки дождитесь подтверждения администратором.</p>
              <label>Email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              <label>Пароль</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
              <label>Подтверждение пароля</label>
              <input type="password" value={password2} onChange={(e) => setPassword2(e.target.value)} />
              <div className="modal-footer auth-modal-footer">
                <Button variant="primary" disabled={busy} onClick={() => void handleRegister()}>
                  Зарегистрироваться
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
