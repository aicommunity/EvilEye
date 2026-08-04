import { Navigate } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { useI18n } from '../i18n';
import type { ReactNode } from 'react';

export function RequirePermission({
  permission,
  children,
  fallback = '/',
}: {
  permission: string;
  children: ReactNode;
  fallback?: string;
}) {
  const { loading, hasPermission } = useAuth();
  const { t } = useI18n();
  if (loading) return <p className="hint">{t('common.loading')}</p>;
  if (!hasPermission(permission)) return <Navigate to={fallback} replace />;
  return <>{children}</>;
}
