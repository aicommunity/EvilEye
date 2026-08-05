import { request, type RequestOptions } from './client';
import type { OverviewResponse, StateCamera, StateRun } from './types';

export const stateApi = {
  overview(opts?: RequestOptions): Promise<OverviewResponse> {
    return request('/state/overview', opts);
  },
  runs(scope: 'current' | 'active' | 'history' | 'all' = 'current', opts?: RequestOptions) {
    return request<{ current_run?: StateRun | null; items?: StateRun[] } | StateRun[]>(
      `/state/runs?scope=${scope}`,
      opts,
    );
  },
  run(rid: number, opts?: RequestOptions): Promise<StateRun> {
    return request(`/state/runs/${rid}`, opts);
  },
  cameras(scope: 'current' | 'active' | 'all' = 'current', opts?: RequestOptions): Promise<{ items: StateCamera[] }> {
    return request(`/state/cameras?scope=${scope}`, opts);
  },
};
