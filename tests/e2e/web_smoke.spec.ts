import { test, expect } from '@playwright/test';

/**
 * Smoke: requires API+static on BASE_URL (default http://127.0.0.1:8181).
 * Optional credentials: EVILEYE_E2E_USER / EVILEYE_E2E_PASSWORD.
 * Skip gracefully when server is down.
 */
const BASE = process.env.EVILEYE_E2E_BASE || 'http://127.0.0.1:8181';
const USER = process.env.EVILEYE_E2E_USER || 'admin';
const PASS = process.env.EVILEYE_E2E_PASSWORD || 'admin';

test.describe('web smoke', () => {
  test('serves SPA shell or redirects to login', async ({ page }) => {
    const res = await page.goto(BASE + '/live', { waitUntil: 'domcontentloaded' }).catch(() => null);
    test.skip(!res, 'server not running');
    expect(res!.status()).toBeLessThan(500);
    await expect(page.locator('#root')).toBeVisible({ timeout: 5000 });
  });

  test('ready endpoint', async ({ request }) => {
    const res = await request.get(BASE + '/ready').catch(() => null);
    test.skip(!res, 'server not running');
    expect(res!.ok()).toBeTruthy();
  });

  test('login → live → events detail path', async ({ page }) => {
    const ready = await page.request.get(BASE + '/ready').catch(() => null);
    test.skip(!ready?.ok(), 'server not running');

    await page.goto(BASE + '/live', { waitUntil: 'domcontentloaded' });

    // Auth may be disabled — then Live is already visible.
    const loginVisible = await page
      .locator('input[type="password"], input[name="password"], input[placeholder*="парол" i]')
      .first()
      .isVisible()
      .catch(() => false);

    if (loginVisible) {
      const userInput = page
        .locator('input[name="username"], input[name="email"], input[type="text"], input[placeholder*="логин" i], input[placeholder*="user" i]')
        .first();
      const passInput = page.locator('input[type="password"]').first();
      await userInput.fill(USER);
      await passInput.fill(PASS);
      await page.locator('button[type="submit"], button:has-text("Войти"), button:has-text("Login")').first().click();
      await page.waitForTimeout(800);
    }

    // Live workspace
    await page.goto(BASE + '/live', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#root')).toBeVisible();
    const liveHeading = page.getByRole('heading', { name: /Live/i }).or(page.locator('h2', { hasText: /Live/i }));
    await expect(liveHeading.first()).toBeVisible({ timeout: 8000 });

    // Events page
    await page.goto(BASE + '/events', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: /Журнал/i }).or(page.locator('h2', { hasText: /Журнал/i })).first()).toBeVisible({
      timeout: 8000,
    });

    // Open first journal row if present (detail drawer)
    const row = page.locator('.journal-table tbody tr, .journal-row, button:has-text("Событие")').first();
    if (await row.isVisible().catch(() => false)) {
      await row.click();
      await expect(
        page.locator('.journal-detail-modal, .modal.open, [role="dialog"]').first(),
      ).toBeVisible({ timeout: 5000 });
    }
  });
});
