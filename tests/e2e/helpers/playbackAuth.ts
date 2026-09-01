import { APIRequestContext, Browser, BrowserContext, Page } from '@playwright/test';

export const BASE = process.env.EVILEYE_E2E_BASE || 'http://127.0.0.1:8181';

export type PlaybackCredentials = {
  user: string;
  password: string;
};

export const defaultUserCreds = (): PlaybackCredentials => ({
  user: process.env.EVILEYE_E2E_USER || 'admin',
  password: process.env.EVILEYE_E2E_PASSWORD || 'admin',
});

export const adminCreds = (): PlaybackCredentials => ({
  user: process.env.EVILEYE_E2E_ADMIN_USER || 'admin',
  password: process.env.EVILEYE_E2E_ADMIN_PASSWORD || 'admin',
});

/** Playwright omits Secure cookies on http:// — relax for LAN lab tests. */
export async function relaxSecureCookiesForHttp(context: BrowserContext): Promise<void> {
  if (!BASE.startsWith('http://')) return;
  const cookies = await context.cookies();
  if (!cookies.length) return;
  await context.clearCookies();
  await context.addCookies(cookies.map((cookie) => ({ ...cookie, secure: false })));
}

export async function loginViaApi(
  request: APIRequestContext,
  creds: PlaybackCredentials = defaultUserCreds(),
  browserContext?: BrowserContext,
): Promise<boolean> {
  const res = await request
    .post(`${BASE}/api/v1/auth/login`, {
      data: { username: creds.user, password: creds.password },
    })
    .catch(() => null);
  if (!res?.ok()) return false;
  if (browserContext) await relaxSecureCookiesForHttp(browserContext);
  return true;
}

export type IsolatedApiSession = {
  request: APIRequestContext;
  context: BrowserContext;
  close: () => Promise<void>;
};

export async function createIsolatedApiSession(
  browser: Browser,
  creds: PlaybackCredentials,
): Promise<IsolatedApiSession | null> {
  const context = await browser.newContext({ baseURL: BASE });
  const logged = await loginViaApi(context.request, creds, context);
  if (!logged) {
    await context.close();
    return null;
  }
  return {
    request: context.request,
    context,
    close: () => context.close(),
  };
}

export async function maybeLoginUi(page: Page, creds: PlaybackCredentials = defaultUserCreds()): Promise<void> {
  const dialog = page.locator('.auth-modal-content').first();
  const loginVisible = await dialog.isVisible().catch(() => false);
  if (!loginVisible) {
    const passOnly = page.locator('input[type="password"]').first();
    const passVisible = await passOnly.isVisible().catch(() => false);
    if (!passVisible) return;
    const userInput = page
      .locator(
        'input[name="username"], input[name="email"], input[type="text"], input[placeholder*="логин" i]',
      )
      .first();
    if (await userInput.isVisible().catch(() => false)) {
      await userInput.fill(creds.user);
    }
    await passOnly.fill(creds.password);
    const submit = page
      .locator('button[type="submit"], button:has-text("Войти"), button:has-text("Login")')
      .first();
    if (await submit.isVisible().catch(() => false)) {
      await submit.click();
    } else {
      await passOnly.press('Enter').catch(() => undefined);
    }
    await page.waitForTimeout(800);
    await relaxSecureCookiesForHttp(page.context());
    return;
  }

  const userInput = dialog.locator('input').nth(0);
  const passInput = dialog.locator('input[type="password"]').first();
  await userInput.fill(creds.user);
  await passInput.fill(creds.password);
  const submit = dialog
    .locator('.auth-modal-footer button, button:has-text("Войти"), button:has-text("Login")')
    .first();
  await submit.click();
  await page.waitForTimeout(1200);
  await relaxSecureCookiesForHttp(page.context());
}

export async function ensureServerReady(request: APIRequestContext): Promise<boolean> {
  const ready = await request.get(`${BASE}/ready`).catch(() => null);
  return Boolean(ready?.ok());
}

export async function clearServerMemoryCache(request: APIRequestContext): Promise<boolean> {
  const res = await request
    .post(`${BASE}/api/v1/playback/_debug/clear-memory-cache`)
    .catch(() => null);
  return Boolean(res?.ok());
}
