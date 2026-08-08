import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { authApi, ApiError, type AuthUser } from '../api';

interface AuthState {
  loading: boolean;
  authEnabled: boolean;
  user: AuthUser | null;
  permissions: Set<string>;
  refresh: () => Promise<boolean>;
  login: (username: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<string>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [authEnabled, setAuthEnabled] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [permissions, setPermissions] = useState<Set<string>>(new Set());

  const apply = useCallback((enabled: boolean, nextUser: AuthUser | null, perms: string[]) => {
    setAuthEnabled(enabled);
    setUser(nextUser);
    setPermissions(new Set(perms));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const me = await authApi.me();
      apply(me.auth_enabled, me.user, me.permissions ?? []);
      setLoading(false);
      if (!me.auth_enabled) return true;
      return Boolean(me.user);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        apply(true, null, []);
        setLoading(false);
        return false;
      }
      setLoading(false);
      return false;
    }
  }, [apply]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (username: string, password: string) => {
      const result = await authApi.login(username, password);
      apply(result.auth_enabled, result.user, result.permissions ?? []);
    },
    [apply],
  );

  const register = useCallback(async (email: string, password: string) => {
    const result = await authApi.register(email, password);
    return result.message || '';
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    apply(authEnabled, null, []);
  }, [apply, authEnabled]);

  const hasPermission = useCallback(
    (permission: string) => {
      if (!authEnabled) return true;
      return permissions.has(permission) || permissions.has('system:admin');
    },
    [authEnabled, permissions],
  );

  const value = useMemo(
    () => ({
      loading,
      authEnabled,
      user,
      permissions,
      refresh,
      login,
      register,
      logout,
      hasPermission,
    }),
    [loading, authEnabled, user, permissions, refresh, login, register, logout, hasPermission],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
