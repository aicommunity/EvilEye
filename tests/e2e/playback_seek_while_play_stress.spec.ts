import { test, expect } from '@playwright/test';

/**
 * Seek-while-play stress: Play + rapid timeline clicks must not freeze the playhead.
 *
 * Env:
 * - EVILEYE_E2E_BASE (default http://127.0.0.1:8181)
 * - EVILEYE_E2E_USER / EVILEYE_E2E_PASSWORD
 * - E2E_SEEKPLAY_DATE
 * - E2E_SEEKPLAY_SEEKS (default 12)
 * - E2E_SEEKPLAY_INTERVAL_MS (default 350)
 */
const BASE = process.env.EVILEYE_E2E_BASE || 'http://127.0.0.1:8181';
const USER = process.env.EVILEYE_E2E_USER || 'admin';
const PASS = process.env.EVILEYE_E2E_PASSWORD || 'admin';
const SEEKPLAY_DATE = process.env.E2E_SEEKPLAY_DATE || new Date().toISOString().slice(0, 10);
const STORM_SEEKS = Number(process.env.E2E_SEEKPLAY_SEEKS || '12');
const INTERVAL_MS = Number(process.env.E2E_SEEKPLAY_INTERVAL_MS || '350');

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

async function videoProbe(page: any) {
  return page.evaluate(() => {
    const videos = [...document.querySelectorAll('video')].map((v) => ({
      paused: v.paused,
      seeking: v.seeking,
      readyState: v.readyState,
      currentTime: v.currentTime,
      duration: Number.isFinite(v.duration) ? v.duration : null,
    }));
    const dbg = (window as any).__playbackDebug;
    return {
      videos,
      clock: document.querySelector('.playback-position-clock')?.textContent ?? null,
      counters: dbg?.counters ? { ...dbg.counters } : null,
      settleEnter: dbg?.counters?.settleEnter ?? null,
      settleExit: dbg?.counters?.settleExit ?? null,
      anyReady: videos.some((v) => v.readyState >= 2),
      allPaused: videos.length > 0 && videos.every((v) => v.paused),
      anySeeking: videos.some((v) => v.seeking),
    };
  });
}

test.describe('playback seek-while-play stress', () => {
  test('play then rapid seeks keep timeline and video recoverable', async ({ page }) => {
    test.setTimeout(120_000);

    const ready = await page.request.get(BASE + '/ready').catch(() => null);
    test.skip(!ready?.ok(), 'server not running');

    await page.addInitScript(() => {
      try {
        localStorage.setItem('playbackDebug', '1');
      } catch {
        /* ignore */
      }
    });

    const nav = await page.goto(BASE + '/playback', { waitUntil: 'domcontentloaded' }).catch(() => null);
    test.skip(!nav, 'playback page unreachable');
    await maybeLogin(page);

    const dateInput = page.locator('input[type="date"]').first();
    const dateInputVisible = await dateInput.isVisible().catch(() => false);
    test.skip(!dateInputVisible, 'playback controls unavailable (date input missing)');
    await dateInput.fill(SEEKPLAY_DATE);
    await dateInput.dispatchEvent('input');
    await dateInput.dispatchEvent('change');
    await page.waitForTimeout(1500);

    const noData = page.locator('text=/Нет записей|No recordings|Нет данных|No data/i').first();
    if (await noData.isVisible().catch(() => false)) {
      test.skip(true, `no recordings for ${SEEKPLAY_DATE}`);
    }

    const clock = page.locator('.playback-position-clock').first();
    await expect(clock).toBeVisible({ timeout: 15_000 });
    const timeline = page.locator('.playback-timeline').first();
    await expect(timeline).toBeVisible({ timeout: 15_000 });
    const box = await timeline.boundingBox();
    test.skip(!box, 'timeline bounding box missing');
    if (!box) return;

    let playbackFailed = 0;
    let playbackTotal = 0;
    page.on('response', (res) => {
      const url = res.url();
      if (!/\/api\/v1\/playback\//.test(url)) return;
      playbackTotal += 1;
      if (res.status() >= 400) playbackFailed += 1;
    });

    await page.mouse.click(box.x + box.width * 0.4, box.y + box.height * 0.6);
    await page.waitForTimeout(900);

    const playBtn = page
      .locator(
        'button:has-text("Play"), button:has-text("Пауза"), button:has-text("Pause"), button[aria-label*="Play" i], button[title*="Play" i]',
      )
      .first();
    // Toggle play if a dedicated control exists; otherwise click common transport.
    const transport = page.locator('.playback-transport button, .playback-controls button').first();
    if (await playBtn.isVisible().catch(() => false)) {
      const label = ((await playBtn.textContent()) || '').toLowerCase();
      if (!label.includes('pause') && !label.includes('пауза')) {
        await playBtn.click();
      }
    } else if (await transport.isVisible().catch(() => false)) {
      await transport.click();
    }

    // Wait until at least one video is ready or clock is present.
    await expect
      .poll(async () => (await videoProbe(page)).anyReady || (await clock.textContent()), { timeout: 20_000 })
      .toBeTruthy();

    const preStormClock = ((await clock.textContent()) ?? '').trim();
    const pcts = [0.25, 0.55, 0.75, 0.9];
    for (let i = 0; i < STORM_SEEKS; i++) {
      const pct = pcts[i % pcts.length];
      await page.mouse.click(box.x + box.width * pct, box.y + box.height * 0.6);
      await page.waitForTimeout(INTERVAL_MS);
    }

    await page.waitForTimeout(2500);
    const afterStorm = await videoProbe(page);
    if (afterStorm.settleEnter != null && afterStorm.settleExit != null) {
      expect(afterStorm.settleExit).toBeGreaterThanOrEqual(afterStorm.settleEnter);
    }

    // Recovery: not all videos forever seeking.
    await expect
      .poll(async () => !(await videoProbe(page)).anySeeking, { timeout: 5000 })
      .toBeTruthy();

    const controlClockBefore = ((await clock.textContent()) ?? '').trim();
    await page.mouse.click(box.x + box.width * 0.35, box.y + box.height * 0.6);
    await expect
      .poll(async () => ((await clock.textContent()) ?? '').trim(), { timeout: 5000 })
      .not.toBe(controlClockBefore);

    // Soft check: storm should have moved clock at some point (or control seek did).
    const finalClock = ((await clock.textContent()) ?? '').trim();
    expect(finalClock.length).toBeGreaterThan(0);
    expect(finalClock === preStormClock && controlClockBefore === preStormClock).toBe(false);

    if (playbackTotal >= 10) {
      expect(playbackFailed / playbackTotal).toBeLessThan(0.3);
    }
  });
});
