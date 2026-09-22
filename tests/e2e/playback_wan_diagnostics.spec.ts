import { test, expect } from '@playwright/test';
import {
  BASE,
  adminCreds,
  clearServerMemoryCache,
  defaultUserCreds,
  ensureServerReady,
  loginViaApi,
  maybeLoginUi,
} from './helpers/playbackAuth';
import { applyNetworkProfile, resolveNetworkProfile } from './helpers/networkProfiles';
import {
  collectApiTimingsFromPage,
  countSeekingHints,
  playbackCameras,
  playbackDate,
  waitForPlaybackInteractive,
} from './helpers/playbackMetrics';

const DATE = playbackDate();
const PROFILE = resolveNetworkProfile();

async function openPlaybackDay(page: import('@playwright/test').Page, date: string) {
  const nav = await page.goto(`${BASE}/playback`, { waitUntil: 'domcontentloaded' }).catch(() => null);
  if (!nav) return false;

  const datePicker = page.locator('[data-testid="date-picker"]').first();
  const legacyDate = page.locator('input[type="date"]').first();
  if (await datePicker.isVisible().catch(() => false)) {
    await datePicker.click();
    const dayBtn = page.locator(`.date-picker-day[data-date="${date}"]`).first();
    if (await dayBtn.isVisible().catch(() => false)) {
      await dayBtn.click();
    } else {
      await page.keyboard.type(date);
      await page.keyboard.press('Enter');
    }
  } else if (await legacyDate.isVisible().catch(() => false)) {
    await legacyDate.fill(date);
    await legacyDate.dispatchEvent('change');
  }
  await page.waitForTimeout(800);
  return true;
}

test.describe('playback WAN diagnostics', () => {
  test(`day load metrics [${PROFILE}]`, async ({ page, request }) => {
    test.setTimeout(120_000);
    test.skip(!(await ensureServerReady(request)), 'server not running');

    const creds = defaultUserCreds();
    const logged = await loginViaApi(page.request, creds, page.context());
    test.skip(!logged && creds.user !== 'admin', 'test-user login failed');

    await applyNetworkProfile(page, PROFILE);
    const nav = await page.goto(`${BASE}/playback`, { waitUntil: 'domcontentloaded' }).catch(() => null);
    test.skip(!nav, 'playback unreachable');
    if (!logged) await maybeLoginUi(page, creds);

    const timelineReq = page.waitForResponse(
      (r) => r.url().includes('/api/v1/playback/timeline') && r.status() < 500,
      { timeout: 90_000 },
    );
    await openPlaybackDay(page, DATE);
    const timelineRes = await timelineReq.catch(() => null);

    const interactiveMs = await waitForPlaybackInteractive(page, 90_000);
    const apiTimings = await collectApiTimingsFromPage(page);
    const cacheHeader = timelineRes?.headers()['x-playback-cache'];
    let staleTimeline = false;
    if (timelineRes) {
      try {
        const body = await timelineRes.json();
        staleTimeline = Boolean(body?.stale);
      } catch {
        /* ignore */
      }
    }

    const metrics = {
      profile: PROFILE,
      date: DATE,
      timeToInteractiveMs: interactiveMs,
      cacheHeader,
      staleTimeline,
      apiTimings,
      errors503: apiTimings.filter((t) => t.durationMs > 60_000).length,
    };

    console.log('WAN_DAY_LOAD_METRICS', JSON.stringify(metrics));

    if (PROFILE === 'lan') {
      expect(interactiveMs === null || interactiveMs < 60_000).toBeTruthy();
    }
    expect(timelineRes?.status() ?? 0).toBeLessThan(500);
  });

  test(`seek hint toggles [${PROFILE}]`, async ({ page, request }) => {
    test.setTimeout(120_000);
    test.skip(!(await ensureServerReady(request)), 'server not running');

    const creds = defaultUserCreds();
    const logged = await loginViaApi(page.request, creds, page.context());
    if (!logged) await maybeLoginUi(page, creds);

    await page.addInitScript(() => {
      localStorage.setItem('playbackDebug', '1');
    });
    await applyNetworkProfile(page, PROFILE);
    await openPlaybackDay(page, DATE);
    await waitForPlaybackInteractive(page, 90_000);

    const playBtn = page.locator('button.playback-play, [data-testid="playback-play"]').first();
    if (await playBtn.isVisible().catch(() => false)) {
      await playBtn.click();
      await page.waitForTimeout(500);
    }

    const hintMetrics = await countSeekingHints(page, 5, PROFILE === 'wan_bad' ? 600 : 400);
    hintMetrics.profile = PROFILE;
    console.log('WAN_SEEK_HINT_METRICS', JSON.stringify(hintMetrics));

    const maxToggles = PROFILE === 'wan_bad' ? 4 : PROFILE === 'wan_typical' ? 2 : 2;
    expect(hintMetrics.hintToggles).toBeLessThanOrEqual(maxToggles);
  });
});
