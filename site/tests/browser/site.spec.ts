import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('all goal/agent choices produce useful distinct prompts and preserve the brief', async ({ page }) => {
  await page.goto('./');
  await page.getByLabel('The idea').fill('A booking app for independent studios.');
  for (const task of ['build', 'migrate', 'setup']) {
    await page.locator(`input[name="task"][value="${task}"]`).check();
    for (const agent of ['codex', 'claude']) {
      await page.locator(`input[name="agent"][value="${agent}"]`).check();
      const prompt = await page.locator('#generated-prompt').inputValue();
      expect(prompt).toContain('A booking app for independent studios.');
      expect(prompt).toContain(agent === 'codex' ? '$oci-kit' : '/oci-kit');
      expect(prompt).toContain('wait for my approval');
      expect(prompt).toContain('what is still unverified');
    }
  }
  await expect(page.locator('#stack-field')).toBeHidden();
  await expect(page.locator('#next-step-text')).toContainText('readiness checks');
  await page.locator('input[name="task"][value="migrate"]').check();
  await expect(page.locator('#stack-field')).toBeVisible();
  expect(await page.locator('#generated-prompt').inputValue()).toContain('Do not change DNS');
});

test('clipboard success copies the current generated prompt', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto('./');
  await page.getByLabel('The idea').fill('A private research notebook.');
  await page.getByRole('button', { name: 'Copy prompt', exact: true }).click();
  await expect(page.locator('#copy-status')).toContainText('Copied.');
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toEqual(await page.locator('#generated-prompt').inputValue());
});

test('clipboard denial offers a selected-text fallback without losing content', async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(navigator, 'clipboard', { value: { writeText: async () => { throw new Error('Denied'); } } }));
  await page.goto('./');
  await page.getByRole('button', { name: 'Copy prompt', exact: true }).click();
  await expect(page.locator('#copy-status')).toContainText('Clipboard unavailable');
  await expect(page.locator('#generated-prompt')).toBeFocused();
  const selected = await page.locator('#generated-prompt').evaluate((el: HTMLTextAreaElement) => el.selectionEnd - el.selectionStart);
  expect(selected).toBeGreaterThan(100);
});

test('brief stays local, is rendered as text and never enters persistent storage', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', request => requests.push(request.url()));
  await page.goto('./');
  const payload = '<img src="https://invalid.example/private" onerror="window.bad=true">';
  await page.getByLabel('The idea').fill(payload);
  expect(await page.locator('#generated-prompt').inputValue()).toContain(payload);
  expect(await page.evaluate(() => (window as unknown as { bad?: boolean }).bad)).toBeUndefined();
  expect(requests.some(url => url.includes('invalid.example'))).toBe(false);
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain(payload);
  expect(await page.evaluate(() => JSON.stringify(sessionStorage))).not.toContain(payload);
  expect(requests.every(url => new URL(url).hostname === '127.0.0.1')).toBe(true);
});

test('mobile menu, path selection, keyboard and anchor destinations work', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await page.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name: 'Migrate an app' }).click();
  await expect(page).toHaveURL(/#migrate$/);
  await expect(page.locator('#mobile-nav')).toBeHidden();
  await page.getByRole('link', { name: 'Map my migration' }).click();
  await expect(page.locator('input[name="task"][value="migrate"]')).toBeChecked();
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await page.keyboard.press('Escape');
  await expect(page.locator('#mobile-nav')).toBeHidden();
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeFocused();
  const missing = await page.locator('a[href^="#"]').evaluateAll(links => links.map(link => link.getAttribute('href')!).filter(href => href !== '#' && !document.getElementById(href.slice(1))));
  expect(missing).toEqual([]);
});

for (const theme of ['dark', 'light'] as const) {
  for (const width of [390, 1440]) {
    test(`${theme} ${width}px: no overflow and no automated accessibility violations`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
      await page.goto('./');
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
      expect(results.violations).toEqual([]);
    });
  }
}

test('theme choice persists; terminal instructions follow selected agent', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('./');
  await page.getByRole('button', { name: 'Switch to light theme' }).click();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await page.locator('input[name="agent"][value="claude"]').check();
  await page.getByText('Prefer the terminal?', { exact: true }).click();
  await expect(page.locator('#install-command')).toContainText('--agent claude');
  await expect(page.locator('#agent-entry')).toHaveText('/oci-kit');
});

test('without JavaScript the default prompt and guides remain usable', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:4321/oci-founder-kit/');
  await expect(page.locator('noscript .notice')).toBeVisible();
  await expect(page.locator('noscript .notice')).toContainText('Enable JavaScript to tailor the prompt');
  expect(await page.locator('#generated-prompt').inputValue()).toContain('$oci-kit');
  await expect(page.getByRole('link', { name: 'Browse the start guide' })).toBeVisible();
  await context.close();
});
