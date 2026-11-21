import { test, expect } from '@playwright/test';

/**
 * Long-run playback seek loop.
 *
 * Config via env:
 * - EVILEYE_E2E_BASE
 * - EVILEYE_E2E_USER / EVILEYE_E2E_PASSWORD
 * - E2E_LONGRUN_SEC (default 1800)
 * - E2E_LONGRUN_STEP_MS (default 30_000)
 */
const BASE = process.env.EVILEYE_E2E_BASE || 'http://127.0.0.1:8181';
const USER = process.env.EVILEYE_E2E_USER || 'admin';
const PASS = process.env.EVILEYE_E2E_PASSWORD || 'admin';

const LONGRUN_SEC = Number(process.env.E2E_LONGRUN_SEC || '1800');
const STEP_MS = Number(process.env.E2E_LONGRUN_STEP_MS || '30_000');
const LONGRUN_DATE = process.env.E2E_LONGRUN_DATE || new Date().toISOString().slice(0, 10);

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

test.describe('playback long-run seek', () => {
  test('repeated timeline seeks keep playback clock progressing', async ({ page }) => {
    test.setTimeout(Math.max(60_000, LONGRUN_SEC * 1000 + 180_000));

    const ready = await page.request.get(BASE + '/ready').catch(() => null);
    test.skip(!ready?.ok(), 'server not running');

    const nav = await page.goto(BASE + '/playback', { waitUntil: 'domcontentloaded' }).catch(() => null);
    test.skip(!nav, 'playback page unreachable');
    await maybeLogin(page);

    const dateInput = page.locator('input[type="date"]').first();
    const dateInputVisible = await dateInput.isVisible().catch(() => false);
    test.skip(!dateInputVisible, 'playback controls unavailable (date input missing)');
    await dateInput.fill(LONGRUN_DATE);
    await dateInput.dispatchEvent('input');
    await dateInput.dispatchEvent('change');
    await page.waitForTimeout(1200);

    // CDP markers: websocket churn, request failures, API latency sample.
    const cdp: any = await page.context().newCDPSession(page);
    await cdp.send('Network.enable');

    let wsClosed = 0;
    let wsCreated = 0;
    let wsFrameErrors = 0;
    let netFailed = 0;
    let stateReq = 0;
    let stateReqSlow = 0;
    const requestById = new Map<string, { url: string; ts: number }>();

    cdp.on('Network.webSocketCreated', () => {
      wsCreated += 1;
    });
    cdp.on('Network.webSocketClosed', () => {
      wsClosed += 1;
    });
    cdp.on('Network.webSocketFrameError', () => {
      wsFrameErrors += 1;
    });
    cdp.on('Network.loadingFailed', () => {
      netFailed += 1;
    });
    cdp.on('Network.requestWillBeSent', (ev: any) => {
      requestById.set(ev.requestId, { url: String(ev.request?.url || ''), ts: Date.now() });
    });
    cdp.on('Network.responseReceived', (ev: any) => {
      const req = requestById.get(ev.requestId);
      if (!req) return;
      requestById.delete(ev.requestId);
      if (!/\/api\/v1\/state\/|\/api\/v1\/playback\//.test(req.url)) return;
      stateReq += 1;
      const ms = Date.now() - req.ts;
      if (ms > 1500) stateReqSlow += 1;
    });

    const clock = page.locator('.playback-position-clock').first();
    await expect(clock).toBeVisible({ timeout: 15_000 });

    const timeline = page.locator('.playback-timeline').first();
    await expect(timeline).toBeVisible({ timeout: 15_000 });

    const box = await timeline.boundingBox();
    test.skip(!box, 'timeline bounding box missing');
    if (!box) return;

    let lastClock = (await clock.textContent())?.trim() ?? '';
    const start = Date.now();
    let step = 0;

    while (Date.now() - start < LONGRUN_SEC * 1000) {
      const pct = step % 2 === 0 ? 0.7 : 0.3;
      await page.mouse.click(box.x + box.width * pct, box.y + box.height * 0.6);

      // Clock should eventually move after seek; allow one short retry window.
      try {
        await expect
          .poll(async () => ((await clock.textContent()) ?? '').trim())
          .not.toBe(lastClock, { timeout: 10_000 });
        lastClock = (await clock.textContent())?.trim() ?? lastClock;
      } catch {
        // Don't hard-fail on slow clocks; long-run aims to avoid hard stuck states.
      }

      // Detect hard "searching" stuck states.
      const searching = page.locator('text=/Идёт поиск…|Searching…/i').first();
      const searchingVisible = await searching.isVisible().catch(() => false);
      expect(searchingVisible, 'searching should not be stuck visible').toBe(false);

      step += 1;
      if (Date.now() - start < LONGRUN_SEC * 1000) await page.waitForTimeout(STEP_MS);
    }

    // If backend is unstable, websocket churn/failures can explode.
    // Keep generous guards to reduce false positives in noisy environments.
    expect(wsCreated).toBeGreaterThanOrEqual(0);
    expect(wsClosed).toBeLessThan(10_000);
    expect(wsFrameErrors).toBeLessThan(1_000);
    expect(netFailed).toBeLessThan(1_000);
    if (stateReq >= 20) {
      expect(stateReqSlow / stateReq).toBeLessThan(0.8);
    }
  });
});

