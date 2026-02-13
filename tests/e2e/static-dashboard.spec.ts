import path from 'node:path';
import { test, expect } from '@playwright/test';

const dashboardPath = path.resolve(__dirname, '../../6030_survey_dashboard.html');
const dashboardUrl = `file://${dashboardPath.replace(/\\/g, '/')}`;

test('static dashboard region panel logs', async ({ page }) => {
  page.on('console', message => {
    const location = message.location();
    const locLabel = location?.url ? `${location.url}:${location.lineNumber ?? 0}:${location.columnNumber ?? 0}` : 'unknown';
    console.log(`[browser:${message.type()}] ${message.text()} @ ${locLabel}`);
  });
  page.on('pageerror', error => {
    console.log('[pageerror]', error.message);
  });

  await page.goto(dashboardUrl);
  await page.waitForLoadState('load');
  await page.waitForTimeout(2000);

  const diagnostics = await page.evaluate(() => ({
    hasApp: typeof window.NoiseSurveyApp !== 'undefined'
  }));
  console.log('[node] app diagnostics:', diagnostics);
  expect(diagnostics.hasApp).toBeTruthy();
});
