import path from 'path';
import { test, expect } from '@playwright/test';

const harnessFile = path.resolve(__dirname, 'app-harness.html');
const harnessUrl = `file://${harnessFile}`;

test.beforeEach(async ({ page }) => {
  await page.goto(harnessUrl);
});

test('parameter selection updates the application state', async ({ page }) => {
  const selectedParameter = page.getByTestId('selected-parameter');
  await expect(selectedParameter).toHaveText('LZeq');

  const select = page.getByTestId('parameter-select');
  await select.selectOption('LCeq');

  await expect(selectedParameter).toHaveText('LCeq');
  await expect(page.getByTestId('view-mode')).toHaveText('log');
});

test('view toggle switches between log and overview modes', async ({ page }) => {
  const toggle = page.getByTestId('view-toggle');
  const viewMode = page.getByTestId('view-mode');

  await expect(toggle).toHaveText('Log View Enabled');
  await expect(viewMode).toHaveText('log');

  await toggle.click();
  await expect(viewMode).toHaveText('overview');
  await expect(toggle).toHaveText('Log View Disabled');

  await toggle.click();
  await expect(viewMode).toHaveText('log');
  await expect(toggle).toHaveText('Log View Enabled');
});

test('users can create, select, and remove regions from the chart', async ({ page }) => {
  const chart = page.getByTestId('chart');
  const regionList = page.getByTestId('region-list');
  const regionCount = page.getByTestId('region-count');

  const box = await chart.boundingBox();
  if (!box) {
    throw new Error('Unable to determine chart bounding box for interaction test.');
  }

  const startX = box.x + box.width * 0.2;
  const endX = box.x + box.width * 0.6;
  const centerY = box.y + box.height / 2;

  await page.keyboard.down('Shift');
  await page.mouse.move(startX, centerY);
  await page.mouse.down();
  await page.mouse.move(endX, centerY);
  await page.mouse.up();
  await page.keyboard.up('Shift');

  await expect(regionCount).toHaveText('1');
  await expect(regionList.locator('.region-entry')).toHaveText(/Region 1: start=\d+ms end=\d+ms/);

  await chart.click({ position: { x: box.width * 0.4, y: box.height / 2 } });
  await expect(page.getByTestId('selected-region')).toHaveText('Selected region: Region 1');
  await expect(page.getByTestId('tap-summary')).toContainText('Active tap');

  await chart.click({ modifiers: ['Control'], position: { x: box.width * 0.4, y: box.height / 2 } });

  await expect(regionCount).toHaveText('0');
  await expect(regionList).toHaveText(/No regions defined/);
  await expect(page.getByTestId('selected-region')).toHaveText('Selected region: none');
});
