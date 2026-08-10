import { useState } from 'react';
import { authApi } from '../api';
import { useAuth } from '../auth/AuthContext';
import { Button } from '../components/ui';
import { useToast } from '../components/ui/Toast';
import { useI18n } from '../i18n';

export function ForcePasswordGate() {
  const { mustChangePassword, user, refresh, logout } = useAuth();
  const { t } = useI18n();
  const { showError, showSuccess } = useToast();
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [newPw2, setNewPw2] = useState('');
  const [saving, setSaving] = useState(false);

  if (!mustChangePassword || !user) return null;

  const onSubmit = async () => {
    if (newPw.length < 8) {
      showError(t('auth.mustChangeMinLength'));
      return;
    }
    if (newPw !== newPw2) {
      showError(t('users.passwordMismatch'));
      return;
    }
    setSaving(true);
    try {
      await authApi.changePassword({ current_password: currentPw, new_password: newPw });
      showSuccess(t('users.passwordChanged'));
      setCurrentPw('');
      setNewPw('');
      setNewPw2('');
      await refresh();
    } catch (e) {
      showError(e instanceof Error ? e.message : t('common.error'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="force-password-gate" role="dialog" aria-modal="true">
      <div className="force-password-card change-password-modal">
        <h2>{t('auth.mustChangeTitle')}</h2>
        <p className="hint">{t('auth.mustChangeHint')}</p>
        <label>
          <span>{t('users.currentPassword')}</span>
          <input
            type="password"
            value={currentPw}
            onChange={(e) => setCurrentPw(e.target.value)}
            autoComplete="current-password"
            autoFocus
          />
        </label>
        <label>
          <span>{t('users.newPassword')}</span>
          <input
            type="password"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            minLength={8}
            autoComplete="new-password"
          />
        </label>
        <label>
          <span>{t('users.confirmPassword')}</span>
          <input
            type="password"
            value={newPw2}
            onChange={(e) => setNewPw2(e.target.value)}
            minLength={8}
            autoComplete="new-password"
          />
        </label>
        <div className="modal-actions">
          <Button variant="outline" disabled={saving} onClick={() => void logout()}>
            {t('shell.logout')}
          </Button>
          <Button disabled={saving || !currentPw || newPw.length < 8} onClick={() => void onSubmit()}>
            {t('users.savePassword')}
          </Button>
        </div>
      </div>
    </div>
  );
}
