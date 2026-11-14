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
      await expect(page.locator('#handoff-path')).toContainText(agent === 'codex' ? 'Codex' : 'Claude Code');
      await expect(page.locator('#resume-prompt')).toHaveValue(/docs\/PROGRESS.md/);
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
  expect(page.url()).not.toContain(encodeURIComponent(payload));
  expect(await page.evaluate(() => JSON.stringify(history.state))).not.toContain(payload);
  expect(await page.locator('#resume-prompt').inputValue()).not.toContain(payload);
  expect(requests.every(url => new URL(url).hostname === '127.0.0.1')).toBe(true);
});

test('mobile menu, path selection, keyboard and anchor destinations work', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await page.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name: 'Migrate an app' }).click();
  await expect(page).toHaveURL(/#migrate\?task=build&agent=codex&stack=existing$/);
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
      await page.locator('#stack').selectOption('taskboard');
      await page.locator('#resume-details summary').click();
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
  await expect(page.locator('#checkpoint-title')).toContainText('running locally');
  await page.locator('#resume-details summary').click();
  await expect(page.locator('#resume-prompt')).toBeVisible();
  expect(await page.locator('#resume-prompt').inputValue()).toContain('docs/PROGRESS.md');
  await expect(page.getByRole('link', { name: 'Create my Taskboard' })).toHaveAttribute('href', /docs\/INSTALL.md#create-a-new-editable-starter$/);
  await expect(page.getByRole('link', { name: 'Browse the start guide' })).toBeVisible();
  await context.close();
});

test('editable Taskboard is opt-in with offline creation and a separate preview command', async ({ page }) => {
  await page.goto('./');
  expect(await page.locator('#generated-prompt').inputValue()).not.toContain('Taskboard');
  await page.getByRole('link', { name: 'Create my Taskboard' }).click();
  await expect(page.locator('#stack')).toHaveValue('taskboard');
  await expect(page.locator('#checkpoint-title')).toContainText('editable Taskboard');
  await expect(page.locator('#generated-prompt')).toHaveValue(/project’s app\/ and terraform\//);
  await page.getByText('Prefer the terminal?', { exact: true }).click();
  await expect(page.locator('#install-command')).toContainText('blueprint.py create fullstack-container');
  await expect(page.locator('#install-command')).not.toContainText('local_preview');
  await expect(page.locator('#taskboard-preview')).toContainText('python3 local_preview.py start');
  await page.locator('input[name="agent"][value="claude"]').check();
  await expect(page.locator('#install-command')).toContainText('--agent claude');
  await page.locator('#stack').selectOption('nextjs');
  await expect(page.locator('#generated-prompt')).toHaveValue(/Next.js and TypeScript/);
  expect(await page.locator('#generated-prompt').inputValue()).not.toContain('blueprint.py create');
  await expect(page.locator('#taskboard-preview')).toBeHidden();
  await page.locator('#stack').selectOption('taskboard');
  await page.locator('input[name="task"][value="migrate"]').check();
  await expect(page.locator('#stack')).toHaveValue('existing');
  await expect(page.locator('#taskboard-option')).toBeDisabled();
  await expect(page.locator('#checkpoint-title')).toContainText('migration assessment');
});

test('bookmark, reload and history restore choices without saving the brief', async ({ page }) => {
  await page.goto('./#start?task=migrate&agent=claude&stack=fastapi');
  await expect(page.locator('input[name="task"][value="migrate"]')).toBeChecked();
  await expect(page.locator('input[name="agent"][value="claude"]')).toBeChecked();
  await expect(page.locator('#stack')).toHaveValue('fastapi');
  await page.getByLabel('The idea').fill('Synthetic project context, never in the URL.');
  await page.locator('input[name="task"][value="build"]').check();
  await page.locator('#stack').selectOption('taskboard');
  const bookmark = page.url();
  expect(bookmark).toMatch(/#start\?task=build&agent=claude&stack=taskboard$/);
  await page.reload();
  await expect(page.locator('#stack')).toHaveValue('taskboard');
  await expect(page.locator('#brief')).toHaveValue('');
  await expect(page.locator('#resume-prompt')).toHaveValue(/project’s Taskboard app\//);
  await page.goBack();
  await expect(page.locator('#stack')).toHaveValue('fastapi');
  await expect(page.locator('input[name="task"][value="build"]')).toBeChecked();
  await page.goBack();
  await expect(page.locator('input[name="task"][value="migrate"]')).toBeChecked();
  await page.goForward();
  await page.goForward();
  await expect(page).toHaveURL(bookmark);
  await expect(page.locator('#stack')).toHaveValue('taskboard');
});

test('page anchors retain selections and keyboard navigation reaches its destination', async ({ page }) => {
  await page.goto('./#start?task=migrate&agent=claude&stack=existing');
  const guideLink = page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Guides', exact: true });
  await guideLink.focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#guides\?task=migrate&agent=claude&stack=existing$/);
  await expect(page.locator('#guides')).toBeFocused();
  await page.reload();
  await expect(page.locator('input[name="task"][value="migrate"]')).toBeChecked();
  await expect(page.locator('input[name="agent"][value="claude"]')).toBeChecked();
  await page.goBack();
  await expect(page).toHaveURL(/#start\?task=migrate&agent=claude&stack=existing$/);
});

test('invalid or private fragment parameters fall back and are discarded', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('./#start?task=wrong&agent=unknown&stack=%3Cscript%3E&brief=do-not-save&token=example');
  await expect(page).toHaveURL(/#start\?task=build&agent=codex&stack=existing$/);
  await expect(page.locator('#brief')).toHaveValue('');
  await expect(page.locator('#checkpoint-title')).toContainText('running locally');
  await page.goto('./#start?task=migrate&agent=claude&stack=taskboard');
  await expect(page.locator('#stack')).toHaveValue('existing');
  expect(errors).toEqual([]);
});

for (const allowed of [true, false]) {
  test(`resume prompt supports keyboard copy with clipboard ${allowed ? 'allowed' : 'denied'}`, async ({ page, context }) => {
    if (allowed) await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    else await page.addInitScript(() => Object.defineProperty(navigator, 'clipboard', { value: { writeText: async () => { throw new Error('Denied'); } } }));
    await page.goto('./#start?task=migrate&agent=claude&stack=existing');
    await page.locator('#resume-details summary').focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('#resume-prompt')).toBeVisible();
    await page.getByRole('button', { name: 'Copy resume prompt' }).focus();
    await page.keyboard.press('Enter');
    const text = await page.locator('#resume-prompt').inputValue();
    expect(text).toContain('/oci-kit');
    expect(text).toContain('Do not change DNS');
    if (allowed) {
      await expect(page.locator('#resume-status')).toContainText('Copied.');
      expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(text);
    } else {
      await expect(page.locator('#resume-status')).toContainText('Clipboard unavailable');
      await expect(page.locator('#resume-prompt')).toBeFocused();
      expect(await page.locator('#resume-prompt').evaluate((el: HTMLTextAreaElement) => el.selectionEnd - el.selectionStart)).toBe(text.length);
    }
  });
}
