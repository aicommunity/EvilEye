import { test, expect } from '@playwright/test';
import {
  BASE,
  adminCreds,
  clearServerMemoryCache,
  createIsolatedApiSession,
  defaultUserCreds,
  ensureServerReady,
  loginViaApi,
} from './helpers/playbackAuth';
import { applyNetworkProfile, resolveNetworkProfile } from './helpers/networkProfiles';
import {
  coldPlaybackDate,
  fetchTimelineTiming,
  playbackCameras,
  playbackDate,
  waitForPlaybackInteractive,
} from './helpers/playbackMetrics';

const DATE = playbackDate();
const COLD_DATE = coldPlaybackDate();
const CAMERAS = playbackCameras();
const PROFILE = resolveNetworkProfile();

async function selectPlaybackDate(page: import('@playwright/test').Page, date: string) {
  const legacyDate = page.locator('input[type="date"]').first();
  const datePicker = page.locator('[data-testid="date-picker"]').first();
  if (await legacyDate.isVisible().catch(() => false)) {
    await legacyDate.fill(date);
    await legacyDate.dispatchEvent('change');
  } else if (await datePicker.isVisible().catch(() => false)) {
    await datePicker.click();
    const dayBtn = page.locator(`.date-picker-day[data-date="${date}"]`).first();
    if (await dayBtn.isVisible().catch(() => false)) {
      await dayBtn.click();
    }
  }
  await page.waitForTimeout(800);
}

test.describe('playback cache diagnostics C1-C6', () => {
  test('C1 cold_server + C2 warm_server API', async ({ browser, request }) => {
    test.skip(!(await ensureServerReady(request)), 'server not running');

    const adminSession = await createIsolatedApiSession(browser, adminCreds());
    test.skip(!adminSession, 'admin login failed');
    const cleared = await clearServerMemoryCache(adminSession.request);
    if (!cleared) {
      console.log('CACHE_NOTE: memory cache clear unavailable (set EVILEYE_PLAYBACK_DEBUG=1)');
    }
    await adminSession.close();

    const userSession = await createIsolatedApiSession(browser, defaultUserCreds());
    test.skip(!userSession, 'test-user login failed');

    const cold = await fetchTimelineTiming(userSession.request, DATE, CAMERAS, userSession.context);
    const warm = await fetchTimelineTiming(userSession.request, DATE, CAMERAS, userSession.context);
    await userSession.close();
    const ratio = warm.durationMs > 0 ? cold.durationMs / warm.durationMs : null;

    console.log('CACHE_C1_C2', JSON.stringify({ scenario: 'C1_C2', cold, warm, ratio, profile: PROFILE }));

    expect(cold.status).toBe(200);
    expect(warm.cacheHeader).toBe('hit');
  });

  test('C3 admin_then_user timeline cache headers', async ({ browser, request }) => {
    test.skip(!(await ensureServerReady(request)), 'server not running');

    const adminSession = await createIsolatedApiSession(browser, adminCreds());
    const userSession = await createIsolatedApiSession(browser, defaultUserCreds());
    test.skip(!adminSession || !userSession, 'login failed');

    const adminAllCams = process.env.E2E_PLAYBACK_ADMIN_CAMERAS || CAMERAS;
    const adminTiming = await fetchTimelineTiming(adminSession.request, DATE, adminAllCams, adminSession.context);
    const userTiming = await fetchTimelineTiming(userSession.request, DATE, CAMERAS, userSession.context);
    await adminSession.close();
    await userSession.close();

    console.log('CACHE_C3', JSON.stringify({ admin: adminTiming, user: userTiming, adminCameras: adminAllCams }));

    expect(adminTiming.status).toBe(200);
    expect(userTiming.status).toBe(200);
  });

  test('C4 user_alone first timeline', async ({ browser, request }) => {
    test.skip(!(await ensureServerReady(request)), 'server not running');
    const userSession = await createIsolatedApiSession(browser, defaultUserCreds());
    test.skip(!userSession, 'user login failed');

    const timing = await fetchTimelineTiming(userSession.request, DATE, CAMERAS, userSession.context);
    await userSession.close();
    console.log('CACHE_C4', JSON.stringify(timing));
    expect(timing.status).toBe(200);
  });

  test('C5 cold_date timeline', async ({ browser, request }) => {
    test.skip(!(await ensureServerReady(request)), 'server not running');
    const userSession = await createIsolatedApiSession(browser, defaultUserCreds());
    test.skip(!userSession, 'user login failed');

    const timing = await fetchTimelineTiming(userSession.request, COLD_DATE, CAMERAS, userSession.context);
    await userSession.close();
    console.log('CACHE_C5', JSON.stringify({ coldDate: COLD_DATE, timing }));
    expect(timing.status).toBe(200);
  });

  test('C6 client_cache repeat visit vs reload', async ({ page, request }) => {
    test.setTimeout(120_000);
    test.skip(!(await ensureServerReady(request)), 'server not running');

    const logged = await loginViaApi(page.request, defaultUserCreds(), page.context());
    test.skip(!logged, 'user login failed');
    await applyNetworkProfile(page, PROFILE);

    let firstMs: number | null = null;
    let secondMs: number | null = null;

    for (let pass = 0; pass < 2; pass += 1) {
      if (pass === 1) {
        await page.reload({ waitUntil: 'domcontentloaded' });
      } else {
        await page.goto(`${BASE}/playback`, { waitUntil: 'domcontentloaded' });
      }
      await selectPlaybackDate(page, DATE);
      const ms = await waitForPlaybackInteractive(page, 90_000);
      if (pass === 0) firstMs = ms;
      else secondMs = ms;
    }

    const ratio = firstMs && secondMs && secondMs > 0 ? firstMs / secondMs : null;
    console.log('CACHE_C6', JSON.stringify({ firstMs, secondMs, ratio, profile: PROFILE }));
    expect(firstMs === null || firstMs < 120_000).toBeTruthy();
  });

  test('admin vs user on wan_bad cold_server', async ({ browser, request }) => {
    test.skip(PROFILE !== 'wan_bad', 'set E2E_NETWORK_PROFILE=wan_bad to run');
    test.skip(!(await ensureServerReady(request)), 'server not running');

    const adminSession = await createIsolatedApiSession(browser, adminCreds());
    const userSession = await createIsolatedApiSession(browser, defaultUserCreds());
    test.skip(!adminSession || !userSession, 'login failed');

    await fetchTimelineTiming(adminSession.request, DATE, CAMERAS, adminSession.context);
    await clearServerMemoryCache(adminSession.request).catch(() => false);
    const userTiming = await fetchTimelineTiming(userSession.request, DATE, CAMERAS, userSession.context);
    await adminSession.close();
    await userSession.close();

    console.log('CACHE_ADMIN_VS_USER_COLD', JSON.stringify({ userTiming }));
    expect(userTiming.status).toBe(200);
  });
});
