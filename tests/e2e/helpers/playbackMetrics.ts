import { APIRequestContext, BrowserContext, Page } from '@playwright/test';
import { BASE, relaxSecureCookiesForHttp } from './playbackAuth';

export type ApiTiming = {
  route: string;
  status: number;
  durationMs: number;
  cacheHeader?: string;
};

export type DayLoadMetrics = {
  profile: string;
  date: string;
  timeToTimelineMs: number | null;
  timeToInteractiveMs: number | null;
  apiTimings: ApiTiming[];
  cacheHeaders: Record<string, string>;
  staleTimeline: boolean;
  errors503: number;
};

export type SeekHintMetrics = {
  profile: string;
  seekCount: number;
  hintToggles: number;
  hintVisibleMs: number;
  playbackDebug?: Record<string, unknown>;
};

export function playbackDate(): string {
  return process.env.E2E_PLAYBACK_DATE || new Date().toISOString().slice(0, 10);
}

export function playbackCameras(): string {
  return process.env.E2E_PLAYBACK_CAMERAS || 'Cam1';
}

export function coldPlaybackDate(): string {
  return process.env.E2E_PLAYBACK_COLD_DATE || playbackDate();
}

export async function waitForPlaybackInteractive(page: Page, timeoutMs = 60_000): Promise<number | null> {
  const t0 = Date.now();
  const timeline = page.locator('.playback-timeline, [data-testid="playback-timeline"]').first();
  const loading = page.locator('text=/Загрузка записи|Loading recording/i').first();
  try {
    await loading.waitFor({ state: 'hidden', timeout: timeoutMs }).catch(() => undefined);
    await timeline.waitFor({ state: 'visible', timeout: timeoutMs });
    return Date.now() - t0;
  } catch {
    return null;
  }
}

export async function collectApiTimingsFromPage(page: Page): Promise<ApiTiming[]> {
  return page.evaluate(() => {
    const entries = performance.getEntriesByType('resource') as PerformanceResourceTiming[];
    return entries
      .filter((e) => /\/api\/v1\/playback\//.test(e.name))
      .map((e) => ({
        route: e.name.split('/api/v1/playback/')[1]?.split('?')[0] || e.name,
        status: 0,
        durationMs: Math.round(e.responseEnd - e.startTime),
      }));
  });
}

export async function fetchTimelineTiming(
  request: APIRequestContext,
  date: string,
  cameras: string,
  browserContext?: BrowserContext,
): Promise<ApiTiming> {
  const url =
    `${BASE}/api/v1/playback/timeline?` +
    `date=${encodeURIComponent(date)}&cameras=${encodeURIComponent(cameras)}` +
    `&from=0&to=86400`;
  const t0 = Date.now();
  const res = await request.get(url).catch(() => null);
  if (browserContext) await relaxSecureCookiesForHttp(browserContext);
  const durationMs = Date.now() - t0;
  if (!res) {
    return { route: 'timeline', status: 0, durationMs };
  }
  const body = await res.json().catch(() => ({}));
  return {
    route: 'timeline',
    status: res.status(),
    durationMs,
    cacheHeader: res.headers()['x-playback-cache'],
    ...(typeof body === 'object' && body && 'stale' in body ? {} : {}),
  };
}

export async function countSeekingHints(page: Page, seeks: number, pauseMs = 400): Promise<SeekHintMetrics> {
  let hintToggles = 0;
  let hintVisibleMs = 0;
  let hintVisibleSince: number | null = null;
  const hint = page.locator('.playback-busy-hint').first();

  for (let i = 0; i < seeks; i++) {
    const timeline = page.locator('.playback-timeline-track, .playback-timeline, [data-testid="playback-timeline"]').first();
    const box = await timeline.boundingBox().catch(() => null);
    if (box) {
      const x = box.x + box.width * (0.15 + (i % 7) * 0.1);
      const y = box.y + box.height * 0.5;
      await page.mouse.click(x, y);
    }
    await page.waitForTimeout(pauseMs);
    const visible = await hint.isVisible().catch(() => false);
    if (visible && hintVisibleSince === null) {
      hintToggles += 1;
      hintVisibleSince = Date.now();
    } else if (!visible && hintVisibleSince !== null) {
      hintVisibleMs += Date.now() - hintVisibleSince;
      hintVisibleSince = null;
    }
  }
  if (hintVisibleSince !== null) {
    hintVisibleMs += Date.now() - hintVisibleSince;
  }

  const playbackDebug = await page
    .evaluate(() => {
      const w = window as unknown as { __playbackDebug?: { snapshot?: () => Record<string, unknown> } };
      return w.__playbackDebug?.snapshot?.() ?? undefined;
    })
    .catch(() => undefined);

  return { profile: '', seekCount: seeks, hintToggles, hintVisibleMs, playbackDebug };
}
