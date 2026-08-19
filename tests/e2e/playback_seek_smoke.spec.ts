import { test, expect } from '@playwright/test';

/**
 * Playback smoke:
 * - requires API+static on BASE_URL
 * - verifies playback timeline renders
 * - performs a couple of timeline clicks and ensures the playback clock updates
 */
const BASE = process.env.EVILEYE_E2E_BASE || 'http://127.0.0.1:8181';
const USER = process.env.EVILEYE_E2E_USER || 'admin';
const PASS = process.env.EVILEYE_E2E_PASSWORD || 'admin';
const DEFAULT_DATES = [new Date().toISOString().slice(0, 10), '2026-08-17', '2026-08-16'];
const DATE_MATRIX = (process.env.E2E_PLAYBACK_DATES || DEFAULT_DATES.join(','))
  .split(',')
  .map((v) => v.trim())
  .filter(Boolean);
const LEGACY_METADATA_CUTOFF = '2026-08-17';

async function maybeLogin(page: any) {
  const loginVisible = await page
    .locator('input[type="password"], input[name="password"], input[placeholder*="парол" i]')
    .first()
    .isVisible()
    .catch(() => false);

  if (!loginVisible) return;

  const userInput = page.locator(
    'input[name="username"], input[name="email"], input[type="text"], input[placeholder*="логин" i], input[placeholder*="user" i]',
  ).first();
  const passInput = page.locator('input[type="password"]').first();

  const userVisible = await userInput.isVisible().catch(() => false);
  if (userVisible) {
    await userInput.fill(USER);
  }
  await passInput.fill(PASS);
  const submit = page.locator('button[type="submit"], button:has-text("Войти"), button:has-text("Login")').first();
  const submitVisible = await submit.isVisible().catch(() => false);
  if (submitVisible) {
    await submit.click();
  } else {
    await passInput.press('Enter').catch(() => undefined);
  }
  await page.waitForTimeout(800);
}

test.describe('playback seek smoke', () => {
  test('playback page loads and timeline seek updates the clock on date matrix', async ({ page }) => {
    const ready = await page.request.get(BASE + '/ready').catch(() => null);
    test.skip(!ready?.ok(), 'server not running');

    const nav = await page.goto(BASE + '/playback', { waitUntil: 'domcontentloaded' }).catch(() => null);
    test.skip(!nav, 'playback page unreachable');
    await maybeLogin(page);

    const dateInput = page.locator('input[type="date"]').first();
    const dateInputVisible = await dateInput.isVisible().catch(() => false);
    test.skip(!dateInputVisible, 'playback controls unavailable (date input missing)');

    for (const dateStr of DATE_MATRIX) {
      const isLegacy = dateStr <= LEGACY_METADATA_CUTOFF;

      await dateInput.fill(dateStr);
      await dateInput.dispatchEvent('input');
      await dateInput.dispatchEvent('change');
      await page.waitForTimeout(1200);

      const noData = page
        .locator('text=/Нет записей|No recordings|Нет данных|No data/i')
        .first();
      if (await noData.isVisible().catch(() => false)) {
        continue;
      }

      const clock = page.locator('.playback-position-clock').first();
      await expect(clock).toBeVisible({ timeout: 15_000 });

      const timeline = page.locator('.playback-timeline').first();
      await expect(timeline).toBeVisible({ timeout: 15_000 });

      const box = await timeline.boundingBox();
      expect(box, `timeline bounding box for ${dateStr}`).not.toBeNull();
      if (!box) continue;

      const t1 = (await clock.textContent())?.trim() ?? '';
      await page.mouse.click(box.x + box.width * 0.7, box.y + box.height * 0.6);

      // For legacy dates we allow weaker metadata invariants (historical format drift),
      // but seek clock still must move eventually.
      await expect
        .poll(async () => ((await clock.textContent()) ?? '').trim())
        .not.toBe(t1, { timeout: isLegacy ? 15_000 : 10_000 });

      const t2 = (await clock.textContent())?.trim() ?? '';
      await page.mouse.click(box.x + box.width * 0.3, box.y + box.height * 0.6);
      await expect
        .poll(async () => ((await clock.textContent()) ?? '').trim())
        .not.toBe(t2, { timeout: isLegacy ? 15_000 : 10_000 });
    }
  });
});

