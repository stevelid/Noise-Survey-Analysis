import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { test, expect } from '@playwright/test';

const dashboardUrl = pathToFileURL(path.resolve('test-results/real-dashboard/dashboard.html')).href;

test('real static dashboard reviews meters, saves escaped notes and scrolls independently', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(dashboardUrl);
  await page.waitForFunction(() => Boolean((window as any).NoiseSurveyApp?.registry?.models?.htmlSidePanel));
  await page.evaluate(() => {
    const app = (window as any).NoiseSurveyApp;
    const start = app.store.getState().view.viewport.min;
    app.store.dispatch(app.actions.regionsAdded(Array.from({ length: 80 }, (_, index) => ({
      id: index + 1, positionId: 'P1', start: start + index * 10000,
      end: start + index * 10000 + 3000, note: `Event ${index + 1}`, categoryId: 'other'
    }))));
    app.store.dispatch(app.actions.regionSelect(1));
  });
  const panel = page.locator('[data-nsa-panel="annotations"]');
  await expect(panel).toBeVisible();
  await panel.locator('.nsa-selected [data-action="cycle-meter"][data-meter="P2"]').click();
  await expect(panel.locator('.nsa-selected [data-meter="P2"]')).toHaveAttribute('aria-label', /present/);
  await panel.locator('[data-action="region-category"]').selectOption('traffic');
  const note = panel.locator('[data-action="region-note"]');
  await note.fill('<traffic & birds>');
  await note.press('Control+Enter');
  await expect(note).toHaveValue('<traffic & birds>');
  await expect(panel.locator('traffic')).toHaveCount(0);
  await panel.locator('.nsa-selected h3').click();
  await page.keyboard.press('Control+z');
  await expect(note).toHaveValue('Event 1');
  await note.fill('Saved on leaving the field');
  await panel.locator('[data-action="select-region"][data-id="2"]').click();
  await expect(panel.locator('[data-action="region-note"]')).toHaveAttribute('data-id', '2');
  expect(await page.evaluate(() => (window as any).NoiseSurveyApp.store.getState().regions.byId[1].note))
    .toBe('Saved on leaving the field');
  await note.fill('Saved before opening actions');
  const secondary = panel.locator('details[data-key="region-secondary"]');
  await secondary.locator(':scope > summary').click();
  await expect(secondary).toHaveAttribute('open', '');
  await note.fill('Saved before moving focus');
  await note.press('Tab');
  await expect(panel.locator('[data-key="region-color:2"]')).toBeFocused();
  const bounds = await panel.boundingBox();
  expect(bounds?.x).toBeLessThan(1300);
  expect((bounds?.x || 0) + (bounds?.width || 0)).toBeLessThanOrEqual(1600);
  const scroll = panel.locator('[data-scroll-key="panel"]');
  const pageY = await page.evaluate(() => window.scrollY);
  await scroll.evaluate(element => { element.scrollTop = 500; });
  expect(await scroll.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
  expect(await page.evaluate(() => window.scrollY)).toBe(pageY);
  await page.screenshot({ path: testInfo.outputPath('main-layout.png') });
  await panel.screenshot({ path: testInfo.outputPath('regions-panel.png') });
  await page.evaluate(() => window.scrollTo(0, 700));
  const toolbar = page.locator('.nsa-dashboard-controls');
  const clearance = async () => {
    const side = await panel.boundingBox(), controls = await toolbar.boundingBox();
    return (side?.y || 0) - (controls?.y || 0) - (controls?.height || 0);
  };
  await expect.poll(clearance).toBeGreaterThanOrEqual(0);
  await expect.poll(clearance).toBeLessThanOrEqual(14);
  await panel.getByRole('tab', { name: 'Markers', exact: true }).click();
  await expect(panel.getByRole('tab', { name: 'Markers', exact: true })).toHaveAttribute('aria-selected', 'true');
  expect(errors).toEqual([]);
});
