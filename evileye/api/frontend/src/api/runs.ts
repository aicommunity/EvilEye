import { request, type RequestOptions } from './client';
import type { ConfigRun } from './types';

export type RuntimeDiagnostics = {
  available: boolean;
  degraded: boolean;
  components: Record<string, unknown>;
};

export function runtimeDiagnostics(opts?: RequestOptions): Promise<RuntimeDiagnostics> {
  return request('/system/runtime', opts);
}

export function runsList(): Promise<Record<number, ConfigRun>> {
  return request('/configs/runs');
}

export function runGet(rid: number): Promise<ConfigRun> {
  return request(`/configs/runs/${rid}`);
}

export function runCreate(payload: {
  name?: string;
  config_name?: string;
  config_body?: Record<string, unknown>;
}): Promise<ConfigRun> {
  return request('/configs/runs', { method: 'POST', body: JSON.stringify(payload) });
}

export function runStart(rid: number): Promise<ConfigRun> {
  return request(`/configs/runs/${rid}/start`, { method: 'POST' });
}

export function runStop(rid: number): Promise<ConfigRun> {
  return request(`/configs/runs/${rid}/stop`, { method: 'POST' });
}

export function runDelete(rid: number): Promise<{ id: number; status: string }> {
  return request(`/configs/runs/${rid}`, { method: 'DELETE' });
}
