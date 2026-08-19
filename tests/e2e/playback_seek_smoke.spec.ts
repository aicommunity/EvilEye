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

  await userInput.fill(USER);
  await passInput.fill(PASS);
  await page.locator('button[type="submit"], button:has-text("Войти"), button:has-text("Login")').first().click();
  await page.waitForTimeout(800);
}

test.describe('playback seek smoke', () => {
  test('playback page loads and timeline seek updates the clock', async ({ page }) => {
    const ready = await page.request.get(BASE + '/ready').catch(() => null);
    test.skip(!ready?.ok(), 'server not running');

    await page.goto(BASE + '/playback', { waitUntil: 'domcontentloaded' });
    await maybeLogin(page);

    const clock = page.locator('.playback-position-clock').first();
    await expect(clock).toBeVisible({ timeout: 15_000 });

    const timeline = page.locator('.playback-timeline').first();
    await expect(timeline).toBeVisible({ timeout: 15_000 });

    const box = await timeline.boundingBox();
    expect(box, 'timeline bounding box').not.toBeNull();
    if (!box) return;

    const t1 = (await clock.textContent())?.trim() ?? '';

    // Click near ~70% and then ~30% of timeline width.
    await page.mouse.click(box.x + box.width * 0.7, box.y + box.height * 0.6);

    await expect
      .poll(async () => ((await clock.textContent()) ?? '').trim())
      .not.toBe(t1, { timeout: 10_000 });

    const t2 = (await clock.textContent())?.trim() ?? '';
    await page.mouse.click(box.x + box.width * 0.3, box.y + box.height * 0.6);

    await expect
      .poll(async () => ((await clock.textContent()) ?? '').trim())
      .not.toBe(t2, { timeout: 10_000 });
  });
});

