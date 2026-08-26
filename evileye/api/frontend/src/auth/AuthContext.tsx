import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { authApi, ApiError, type AuthUser, type UserPrefs } from '../api';

interface AuthState {
  loading: boolean;
  authEnabled: boolean;
  user: AuthUser | null;
  permissions: Set<string>;
  mustChangePassword: boolean;
  allowedCameras: string[];
  cameraAccess: 'all' | 'restricted';
  prefs: UserPrefs | null;
  refresh: () => Promise<boolean>;
  login: (username: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<string>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
  clearMustChangePassword: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

const emptyPrefs = (): UserPrefs => ({
  visible_cameras: null,
  lang: null,
  date_format: null,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [authEnabled, setAuthEnabled] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [permissions, setPermissions] = useState<Set<string>>(new Set());
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [allowedCameras, setAllowedCameras] = useState<string[]>([]);
  const [cameraAccess, setCameraAccess] = useState<'all' | 'restricted'>('restricted');
  const [prefs, setPrefs] = useState<UserPrefs | null>(null);

  const apply = useCallback(
    (
      enabled: boolean,
      nextUser: AuthUser | null,
      perms: string[],
      mustChange = false,
      extra?: {
        allowed_cameras?: string[];
        camera_access?: 'all' | 'restricted';
        prefs?: UserPrefs;
      },
    ) => {
      setAuthEnabled(enabled);
      setUser(nextUser);
      setPermissions(new Set(perms));
      setMustChangePassword(Boolean(enabled && nextUser && mustChange));
      setAllowedCameras(extra?.allowed_cameras ?? []);
      setCameraAccess(extra?.camera_access ?? (enabled ? 'restricted' : 'all'));
      setPrefs(extra?.prefs ?? emptyPrefs());
    },
    [],
  );

  const refresh = useCallback(async () => {
    try {
      const me = await authApi.me();
      apply(me.auth_enabled, me.user, me.permissions ?? [], Boolean(me.must_change_password), {
        allowed_cameras: me.allowed_cameras,
        camera_access: me.camera_access,
        prefs: me.prefs,
      });
      setLoading(false);
      if (!me.auth_enabled) return true;
      return Boolean(me.user);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        apply(true, null, [], false);
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
      apply(
        result.auth_enabled,
        result.user,
        result.permissions ?? [],
        Boolean(result.must_change_password),
        {
          allowed_cameras: result.allowed_cameras,
          camera_access: result.camera_access,
          prefs: result.prefs,
        },
      );
    },
    [apply],
  );

  const register = useCallback(async (email: string, password: string) => {
    const result = await authApi.register(email, password);
    return result.message || '';
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    apply(authEnabled, null, [], false);
  }, [apply, authEnabled]);

  const hasPermission = useCallback(
    (permission: string) => {
      if (!authEnabled) return true;
      return permissions.has(permission) || permissions.has('system:admin');
    },
    [authEnabled, permissions],
  );

  const clearMustChangePassword = useCallback(() => setMustChangePassword(false), []);

  const value = useMemo(
    () => ({
      loading,
      authEnabled,
      user,
      permissions,
      mustChangePassword,
      allowedCameras,
      cameraAccess,
      prefs,
      refresh,
      login,
      register,
      logout,
      hasPermission,
      clearMustChangePassword,
    }),
    [
      loading,
      authEnabled,
      user,
      permissions,
      mustChangePassword,
      allowedCameras,
      cameraAccess,
      prefs,
      refresh,
      login,
      register,
      logout,
      hasPermission,
      clearMustChangePassword,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
