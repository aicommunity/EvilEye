import { useAuth } from '../auth/AuthContext';

export function usePermissions() {
  const { hasPermission, permissions, authEnabled } = useAuth();
  return { hasPermission, permissions, authEnabled };
}
