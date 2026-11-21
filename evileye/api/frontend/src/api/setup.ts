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
  storage_mode?: 'json' | 'database';
  has_sources: boolean;
  source_count: number;
  analytics_enabled: boolean;
  recording_enabled: boolean;
  service?: { hint?: string; installed?: boolean | null };
};

export type BasicAlarmCamera = {
  id: number;
  name: string;
  alarm_enabled?: boolean;
  alarm_schedule?: AlarmSchedule | null;
};

export type BasicSource = {
  id: number;
  name: string;
  /** Extra logical names for split sources (Cam3 when card is Cam2). */
  extra_names?: string[];
  /** All logical source_ids in this capture row (projection-only). */
  logical_ids?: number[];
  type: string;
  address: string | number;
  username?: string;
  password?: string;
  password_set?: boolean;
  record?: boolean;
};

export type AlarmSchedule = {
  enabled: boolean;
  weekdays: number[];
  periods: [string, string][];
  class_ids: number[];
  camera_cooldown_sec?: number;
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
  alarm_schedule?: AlarmSchedule | null;
  alarm_cameras?: BasicAlarmCamera[];
};

export const setupApi = {
  status(config?: string): Promise<SetupStatus> {
    const q = config ? `?config=${encodeURIComponent(config)}` : '';
    return request(`/setup/status${q}`);
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
