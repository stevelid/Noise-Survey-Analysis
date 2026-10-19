import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { test, expect, type Locator, type Page } from '@playwright/test';

const dashboardUrl = pathToFileURL(path.resolve('test-results/real-dashboard/dashboard.html')).href;

async function chooseColour(page: Page, picker: Locator, value: string) {
  await picker.click();
  await page.keyboard.press('Escape');
  // Headless automation cannot choose in the operating system's colour dialog.
  // Verify opening/cancelling, then deliver its native input/change contract;
  // the manual checklist covers choosing the colour in the actual dialog.
  await picker.evaluate((element, colour) => {
    (element as HTMLInputElement).value = colour;
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
  }, value);
}

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
  const metricsToggle = panel.locator('[data-action="metrics-visible"]');
  await expect(metricsToggle).toHaveAttribute('aria-expanded', 'false');
  const actions = panel.locator('details[data-key="region-secondary"]');
  await actions.locator(':scope > summary').click();
  const spectrum = panel.locator('details[data-key="region-spectrum"]');
  await spectrum.locator(':scope > summary').click();
  await expect(spectrum.locator('tbody tr')).not.toHaveCount(0);
  await expect(metricsToggle).toHaveAttribute('aria-expanded', 'false');
  await spectrum.locator(':scope > summary').click();
  await actions.locator(':scope > summary').click();
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
  const scroll = panel.locator('[data-scroll-key="region-list"]');
  expect(await scroll.evaluate(element => element.clientHeight)).toBeGreaterThanOrEqual(200);
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

test('dirty notes save without stealing native category and colour mouse interactions', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto(dashboardUrl);
  await page.waitForFunction(() => Boolean((window as any).NoiseSurveyApp?.registry?.models?.htmlSidePanel));
  await page.evaluate(() => {
    const app = (window as any).NoiseSurveyApp;
    const start = app.store.getState().view.viewport.min;
    app.store.dispatch(app.actions.regionsAdded([
      { id: 1, positionId: 'P1', start, end: start + 3000, note: 'Original note', categoryId: 'other' },
      { id: 2, positionId: 'P1', start: start + 10000, end: start + 13000, note: 'Second note', categoryId: 'other' }
    ]));
    app.store.dispatch(app.actions.regionSelect(1));
  });
  const panel = page.locator('[data-nsa-panel="annotations"]');
  const note = panel.locator('[data-action="region-note"]');
  const category = panel.locator('[data-action="region-category"]');
  await note.fill('Saved before mouse category');
  await category.click();
  await expect(category).toBeFocused();
  const options = await category.evaluate(element => [...(element as HTMLSelectElement).options].map(option => option.value));
  await page.keyboard.press('Home');
  for (let index = 0; index < options.indexOf('traffic'); index++) await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(category).toHaveValue('traffic');
  expect(await page.evaluate(() => (window as any).NoiseSurveyApp.store.getState().regions.byId[1].note))
    .toBe('Saved before mouse category');
  await note.fill('Saved before mouse colour');
  const colour = panel.locator('[data-key="region-color:1"]');
  await chooseColour(page, colour, '#123456');
  await expect(colour).toHaveValue('#123456');
  await panel.locator('.nsa-selected h3').click();
  expect(await page.evaluate(() => (window as any).NoiseSurveyApp.store.getState().regions.byId[1].color)).toBe('#123456');
  await page.keyboard.press('Control+z');
  expect(await page.evaluate(() => (window as any).NoiseSurveyApp.store.getState().regions.byId[1].color)).toBeFalsy();
  expect(await page.evaluate(() => (window as any).NoiseSurveyApp.store.getState().regions.byId[1].note))
    .toBe('Saved before mouse colour');
  await page.keyboard.press('Control+z');
  await expect(note).toHaveValue('Saved before mouse category');
  await note.fill('Saved without changing category');
  await category.click();
  await page.keyboard.press('Escape');
  await panel.locator('.nsa-selected h3').click();
  await expect(panel.locator('[data-action="select-region"][data-id="1"]')).toHaveText('Saved without changing category');
  await note.fill('Saved before selecting the next region');
  await category.click(); await page.keyboard.press('Escape');
  await panel.locator('[data-action="select-region"][data-id="2"]').click();
  await expect(note).toHaveAttribute('data-id', '2');
  await note.fill('Saved before opening actions from category');
  await category.click(); await page.keyboard.press('Escape');
  const secondary = panel.locator('details[data-key="region-secondary"]');
  await secondary.locator(':scope > summary').click();
  await expect(secondary).toHaveAttribute('open', '');
  await note.fill('Saved before colour and region selection');
  const secondColour = panel.locator('[data-key="region-color:2"]');
  await chooseColour(page, secondColour, '#abcdef');
  await panel.locator('[data-action="select-region"][data-id="1"]').click();
  await expect(note).toHaveAttribute('data-id', '1');
  expect(await page.evaluate(() => (window as any).NoiseSurveyApp.store.getState().regions.byId[2].color)).toBe('#abcdef');
  expect(await page.evaluate(() => (window as any).NoiseSurveyApp.store.getState().regions.byId[2].note))
    .toBe('Saved before colour and region selection');
});
