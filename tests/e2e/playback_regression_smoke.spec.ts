import { test, expect } from '@playwright/test';

const BASE = process.env.EVILEYE_E2E_BASE || 'http://127.0.0.1:8181';
const USER = process.env.EVILEYE_E2E_USER || 'admin';
const PASS = process.env.EVILEYE_E2E_PASSWORD || 'admin';
const DEEP_LINK_TS = Number(process.env.E2E_PLAYBACK_DEEP_LINK_TS || '1787102416'); // 2026-08-19 04:20:16 local
const DEEP_LINK_DATE = process.env.E2E_PLAYBACK_DEEP_LINK_DATE || '2026-08-19';
const TODAY_DATE = process.env.E2E_PLAYBACK_TODAY || new Date().toISOString().slice(0, 10);

async function loginViaApi(page: any) {
  const res = await page.request
    .post(BASE + '/api/v1/auth/login', {
      data: { username: USER, password: PASS },
    })
    .catch(() => null);
  if (!res) return false;
  return res.ok();
}

async function maybeLogin(page: any) {
  const dialog = page.locator('.auth-modal-content').first();
  const loginVisible = await dialog.isVisible().catch(() => false);

  if (!loginVisible) return;

  const userInput = dialog.locator('input').nth(0);
  const passInput = dialog.locator('input[type="password"]').first();

  await userInput.fill(USER);
  await passInput.fill(PASS);
  const submit = dialog.locator('.auth-modal-footer button, button:has-text("Войти"), button:has-text("Login")').first();
  await submit.click();
  await page.waitForTimeout(1200);
}

async function ensurePlaybackControls(page: any) {
  // Native <input type="date"> was replaced by DatePickerField (data-testid="date-picker").
  const datePicker = page.locator('[data-testid="date-picker"]').first();
  const dateInput = page.locator('input[type="date"]').first();
  const loginDialog = page.locator('text=/Вход в веб-интерфейс|Login/i').first();
  const pickerVisible = await datePicker.isVisible().catch(() => false);
  if (pickerVisible) return datePicker;
  const legacyVisible = await dateInput.isVisible().catch(() => false);
  if (legacyVisible) return dateInput;
  test.skip(await loginDialog.isVisible().catch(() => false), 'playback auth requires valid EVILEYE_E2E credentials');
  await expect(datePicker).toBeVisible({ timeout: 15_000 });
  return datePicker;
}

async function readPlaybackDateIso(page: any): Promise<string> {
  return page.evaluate(() => {
    const root = document.querySelector('[data-testid="date-picker"]') as HTMLElement | null;
    const selected = root?.querySelector('.date-picker-day.is-selected') as HTMLElement | null;
    // When closed, reconstruct from displayed locale text is fragile; prefer clock date + session.
    const clock = document.querySelector('.playback-position-clock')?.textContent?.trim() || '';
    const m = clock.match(/(\d{2})-(\d{2})-(\d{4})/);
    if (m) return `${m[3]}-${m[2]}-${m[1]}`;
    const m2 = clock.match(/(\d{4})-(\d{2})-(\d{2})/);
    if (m2) return `${m2[1]}-${m2[2]}-${m2[3]}`;
    const native = document.querySelector('input[type="date"]') as HTMLInputElement | null;
    return native?.value || '';
  });
}

test.describe('playback regression smoke', () => {
  test('deep-link timestamp switches playback date and keeps camera list alive', async ({ page }) => {
    const ready = await page.request.get(BASE + '/ready').catch(() => null);
    test.skip(!ready?.ok(), 'server not running');

    const apiLogged = await loginViaApi(page);
    const nav = await page.goto(`${BASE}/playback?t=${DEEP_LINK_TS}`, { waitUntil: 'domcontentloaded' }).catch(() => null);
    test.skip(!nav, 'playback page unreachable');
    if (!apiLogged) await maybeLogin(page);

    await ensurePlaybackControls(page);
    await expect
      .poll(async () => readPlaybackDateIso(page))
      .toBe(DEEP_LINK_DATE, { timeout: 20_000 });

    const clock = page.locator('.playback-position-clock').first();
    await expect
      .poll(async () => ((await clock.textContent()) || '').includes('19') && ((await clock.textContent()) || '').includes('2026'))
      .toBe(true, { timeout: 20_000 });

    await expect
      .poll(async () => page.locator('button.btn.btn-sm').filter({ hasText: /^Cam/ }).count())
      .toBeGreaterThan(0, { timeout: 20_000 });

    await expect(page.locator('text=/Нет камер за выбранную дату|No cameras for the selected date/i')).toHaveCount(0);
  });

  test('today playback avoids opening non-finalized segments', async ({ page }) => {
    const ready = await page.request.get(BASE + '/ready').catch(() => null);
    test.skip(!ready?.ok(), 'server not running');

    const apiLogged = await loginViaApi(page);
    const camsRes = await page.request.get(`${BASE}/api/v1/playback/cameras?date=${TODAY_DATE}`).catch(() => null);
    test.skip(!camsRes?.ok(), 'playback cameras unavailable');
    const camsJson = await camsRes!.json();
    const camIds = (camsJson.items || []).map((c: any) => String(c.id || '')).filter(Boolean);
    test.skip(!camIds.length, 'no playback cameras for today');

    let targetCamera: string | null = null;
    let targetTs: number | null = null;
    for (const cam of camIds.slice(0, 5)) {
      const segRes = await page.request
        .get(
          `${BASE}/api/v1/playback/segments?camera=${encodeURIComponent(cam)}&date=${TODAY_DATE}`,
        )
        .catch(() => null);
      if (!segRes?.ok()) continue;
      const segJson = await segRes.json();
      const items = Array.isArray(segJson.items) ? segJson.items : [];
      const pending = items.find((s: any) => s && s.playable === false);
      if (pending) {
        targetCamera = cam;
        targetTs = Number(pending.start_ts || 0) + 1;
        break;
      }
    }
    test.skip(!(targetCamera && targetTs), 'no in-progress playback segment found for today');

    const nav = await page.goto(`${BASE}/playback?t=${Math.floor(targetTs!)}`, { waitUntil: 'domcontentloaded' }).catch(() => null);
    test.skip(!nav, 'playback page unreachable');
    if (!apiLogged) await maybeLogin(page);

    await ensurePlaybackControls(page);
    // Date is already driven by deep-link `t=`; avoid filling readonly DatePickerField.
    await expect
      .poll(async () => readPlaybackDateIso(page))
      .toBe(TODAY_DATE, { timeout: 20_000 });

    await expect
      .poll(async () => page.locator('button.btn.btn-sm').filter({ hasText: /^Cam/ }).count())
      .toBeGreaterThan(0, { timeout: 20_000 });

    await expect
      .poll(async () =>
        page.evaluate((cam) => {
          const cards = Array.from(document.querySelectorAll('.playback-cell, .camera-card')) as HTMLElement[];
          const card = cards.find((el) => (el.textContent || '').includes(cam));
          const videos = card ? (Array.from(card.querySelectorAll('video')) as HTMLVideoElement[]) : [];
          return videos.filter((v) => v.error != null).length;
        }, targetCamera),
      )
      .toBe(0, { timeout: 20_000 });
  });
});
