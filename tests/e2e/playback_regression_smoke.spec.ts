import { test, expect } from '@playwright/test';

const BASE = process.env.EVILEYE_E2E_BASE || 'http://127.0.0.1:8181';
const USER = process.env.EVILEYE_E2E_USER || 'admin';
const PASS = process.env.EVILEYE_E2E_PASSWORD || 'admin';
const DEEP_LINK_TS = Number(process.env.E2E_PLAYBACK_DEEP_LINK_TS || '1787102416'); // 2026-08-19 04:20:16 local
const DEEP_LINK_DATE = process.env.E2E_PLAYBACK_DEEP_LINK_DATE || '2026-08-19';
const TODAY_DATE = process.env.E2E_PLAYBACK_TODAY || new Date().toISOString().slice(0, 10);

async function maybeLogin(page: any) {
  const loginVisible = await page
    .locator('input[type="password"], input[name="password"], input[placeholder*="парол" i]')
    .first()
    .isVisible()
    .catch(() => false);

  if (!loginVisible) return;

  const userInput = page
    .locator(
      'input[name="username"], input[name="email"], input[type="text"], input[placeholder*="логин" i], input[placeholder*="user" i]',
    )
    .first();
  const passInput = page.locator('input[type="password"]').first();

  if (await userInput.isVisible().catch(() => false)) {
    await userInput.fill(USER);
  }
  await passInput.fill(PASS);
  const submit = page.locator('button[type="submit"], button:has-text("Войти"), button:has-text("Login")').first();
  if (await submit.isVisible().catch(() => false)) {
    await submit.click();
  } else {
    await passInput.press('Enter').catch(() => undefined);
  }
  await page.waitForTimeout(1000);
}

async function ensurePlaybackControls(page: any) {
  const dateInput = page.locator('input[type="date"]').first();
  const loginDialog = page.locator('text=/Вход в веб-интерфейс|Login/i').first();
  const visible = await dateInput.isVisible().catch(() => false);
  if (visible) return dateInput;
  test.skip(await loginDialog.isVisible().catch(() => false), 'playback auth requires valid EVILEYE_E2E credentials');
  await expect(dateInput).toBeVisible({ timeout: 15_000 });
  return dateInput;
}

test.describe('playback regression smoke', () => {
  test('deep-link timestamp switches playback date and keeps camera list alive', async ({ page }) => {
    const ready = await page.request.get(BASE + '/ready').catch(() => null);
    test.skip(!ready?.ok(), 'server not running');

    const nav = await page.goto(`${BASE}/playback?t=${DEEP_LINK_TS}`, { waitUntil: 'domcontentloaded' }).catch(() => null);
    test.skip(!nav, 'playback page unreachable');
    await maybeLogin(page);

    const dateInput = await ensurePlaybackControls(page);
    await expect(dateInput).toHaveValue(DEEP_LINK_DATE, { timeout: 20_000 });

    const clock = page.locator('.playback-position-clock').first();
    await expect(clock).toContainText('2026-08-19', { timeout: 20_000 });

    await expect
      .poll(async () => page.locator('button.btn.btn-sm').filter({ hasText: /^Cam/ }).count())
      .toBeGreaterThan(0, { timeout: 20_000 });

    await expect(page.locator('text=/Нет камер за выбранную дату|No cameras for the selected date/i')).toHaveCount(0);
  });

  test('today playback avoids opening non-finalized segments', async ({ page }) => {
    const ready = await page.request.get(BASE + '/ready').catch(() => null);
    test.skip(!ready?.ok(), 'server not running');

    const nav = await page.goto(`${BASE}/playback`, { waitUntil: 'domcontentloaded' }).catch(() => null);
    test.skip(!nav, 'playback page unreachable');
    await maybeLogin(page);

    const dateInput = await ensurePlaybackControls(page);
    await dateInput.fill(TODAY_DATE);
    await dateInput.dispatchEvent('input');
    await dateInput.dispatchEvent('change');

    await expect
      .poll(async () => page.locator('button.btn.btn-sm').filter({ hasText: /^Cam/ }).count())
      .toBeGreaterThan(0, { timeout: 20_000 });

    const recordingBanner = page.locator('.playback-recording-banner, .camera-preview-empty').filter({
      hasText: /Идёт запись|Recording in progress/i,
    });
    await expect(recordingBanner.first()).toBeVisible({ timeout: 20_000 });

    const erroredVideos = await page.evaluate(() =>
      Array.from(document.querySelectorAll('video')).filter((v) => (v as HTMLVideoElement).error != null).length,
    );
    expect(erroredVideos).toBe(0);
  });
});
