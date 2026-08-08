import { request } from './client';

export type SetupStatus = {
  needs_setup: boolean;
  configured: boolean;
  ready_to_run: boolean;
  must_change_password: boolean;
  default_config: string;
  data_dir: string;
  data_dir_confirmed: boolean;
  use_database: boolean;
  has_sources: boolean;
  source_count: number;
  analytics_enabled: boolean;
  recording_enabled: boolean;
  service?: { hint?: string; installed?: boolean | null };
};

export type BasicSource = {
  id: number;
  name: string;
  type: string;
  address: string | number;
  username?: string;
  password?: string;
  password_set?: boolean;
  record?: boolean;
};

export type BasicSetup = {
  config_name: string;
  data_dir: string;
  storage_mode: 'json' | 'database';
  database: {
    host_name: string;
    port: number;
    database_name: string;
    user_name: string;
    password?: string;
    password_set?: boolean;
  };
  sources: BasicSource[];
  analytics_enabled: boolean;
  recording_enabled: boolean;
};

export const setupApi = {
  status(): Promise<SetupStatus> {
    return request('/setup/status');
  },
  basicGet(config?: string): Promise<BasicSetup> {
    const q = config ? `?config=${encodeURIComponent(config)}` : '';
    return request(`/setup/basic${q}`);
  },
  basicPut(body: BasicSetup): Promise<{ ok: boolean; status: SetupStatus; basic: BasicSetup }> {
    return request('/setup/basic', { method: 'PUT', body: JSON.stringify(body) });
  },
  checkDataDir(path: string): Promise<{
    ok: boolean;
    writable: boolean;
    free_bytes: number;
    message: string;
    resolved?: string;
  }> {
    return request('/setup/check-data-dir', { method: 'POST', body: JSON.stringify({ path }) });
  },
  testDatabase(body: BasicSetup['database'] & { password?: string }): Promise<{ ok: boolean; message: string }> {
    return request('/setup/test-database', { method: 'POST', body: JSON.stringify(body) });
  },
};
