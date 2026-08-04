import { Navigate } from 'react-router-dom';
import { useAuth } from './AuthContext';
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
  if (loading) return <p className="hint">Загрузка…</p>;
  if (!hasPermission(permission)) return <Navigate to={fallback} replace />;
  return <>{children}</>;
}
