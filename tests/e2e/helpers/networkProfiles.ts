import { CDPSession, Page } from '@playwright/test';

export type NetworkProfileName = 'lan' | 'wan_typical' | 'wan_bad' | 'wan_lossy' | 'offline';

export type NetworkProfile = {
  offline: boolean;
  latency: number;
  downloadThroughput: number;
  uploadThroughput: number;
};

/** CDP Network.emulateNetworkConditions profiles (bytes/s for throughput). */
export const NETWORK_PROFILES: Record<NetworkProfileName, NetworkProfile> = {
  lan: {
    offline: false,
    latency: 5,
    downloadThroughput: (50 * 1024 * 1024) / 8,
    uploadThroughput: (20 * 1024 * 1024) / 8,
  },
  wan_typical: {
    offline: false,
    latency: 150,
    downloadThroughput: (5 * 1024 * 1024) / 8,
    uploadThroughput: (1 * 1024 * 1024) / 8,
  },
  wan_bad: {
    offline: false,
    latency: 300,
    downloadThroughput: (1 * 1024 * 1024) / 8,
    uploadThroughput: (512 * 1024) / 8,
  },
  wan_lossy: {
    offline: false,
    latency: 200,
    downloadThroughput: (3 * 1024 * 1024) / 8,
    uploadThroughput: (1 * 1024 * 1024) / 8,
  },
  offline: {
    offline: true,
    latency: 0,
    downloadThroughput: 0,
    uploadThroughput: 0,
  },
};

export function resolveNetworkProfile(): NetworkProfileName {
  const raw = (process.env.E2E_NETWORK_PROFILE || 'lan').trim().toLowerCase();
  if (raw in NETWORK_PROFILES) return raw as NetworkProfileName;
  return 'lan';
}

export async function applyNetworkProfile(page: Page, profile: NetworkProfileName): Promise<CDPSession> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  const cfg = NETWORK_PROFILES[profile];
  await cdp.send('Network.emulateNetworkConditions', {
    offline: cfg.offline,
    latency: cfg.latency,
    downloadThroughput: cfg.downloadThroughput,
    uploadThroughput: cfg.uploadThroughput,
    connectionType: 'cellular3g',
  });
  return cdp;
}
