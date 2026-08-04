import { test, expect } from '@playwright/test';

/**
 * Smoke: requires API+static on BASE_URL (default http://127.0.0.1:8181).
 * Skip gracefully when server is down.
 */
const BASE = process.env.EVILEYE_E2E_BASE || 'http://127.0.0.1:8181';

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
});
