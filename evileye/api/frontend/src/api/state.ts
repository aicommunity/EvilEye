import { request } from './client';
import type { OverviewResponse, StateCamera, StateRun } from './types';

export const stateApi = {
  overview(): Promise<OverviewResponse> {
    return request('/state/overview');
  },
  runs(scope: 'current' | 'active' | 'history' | 'all' = 'current') {
    return request<{ items?: StateRun[] } | StateRun[]>(`/state/runs?scope=${scope}`);
  },
  run(rid: number): Promise<StateRun> {
    return request(`/state/runs/${rid}`);
  },
  cameras(scope: 'current' | 'active' | 'all' = 'current'): Promise<{ items: StateCamera[] }> {
    return request(`/state/cameras?scope=${scope}`);
  },
};
