import fs from 'node:fs';
import path from 'node:path';
import { test, expect, type ConsoleMessage, type Page } from '@playwright/test';

const harnessFile = path.resolve(__dirname, 'app-harness.html');
const harnessUrl = `file://${harnessFile}`;
const logFilePath = path.resolve(__dirname, '../../playwright-console.log');

type ConsoleLogMetadata = {
  stream: fs.WriteStream;
  handler: (msg: ConsoleMessage) => void;
};

const logMetadata = new WeakMap<Page, ConsoleLogMetadata>();

function formatLocation(message: ConsoleMessage): string {
  const location = message.location();
  if (!location.url) {
    return 'unknown';
  }
  const line = location.lineNumber ?? 0;
  const column = location.columnNumber ?? 0;
  return `${location.url}:${line}:${column}`;
}

test.beforeEach(async ({ page }, testInfo) => {
  const stream = fs.createWriteStream(logFilePath, { flags: 'a' });
  const testId = testInfo.titlePath.join(' > ');
  const baseLabel = `[worker:${testInfo.workerIndex}] [project:${testInfo.project.name}] [test:${testId}]`;
  const beginLine = `[${new Date().toISOString()}] ${baseLabel} BEGIN_BROWSER_CONSOLE`;
  stream.write(`${beginLine}\n`);

  const handler = (msg: ConsoleMessage) => {
    const timestamp = new Date().toISOString();
    const entry = `[${timestamp}] ${baseLabel} [${msg.type()}] ${msg.text()} @ ${formatLocation(msg)}`;
    stream.write(`${entry}\n`);
    process.stdout.write(`${entry}\n`);
  };

  page.on('console', handler);
  logMetadata.set(page, { stream, handler });

  await page.goto(harnessUrl);
});

test.afterEach(async ({ page }, testInfo) => {
  const metadata = logMetadata.get(page);
  if (!metadata) {
    return;
  }
  page.off('console', metadata.handler);
  const testId = testInfo.titlePath.join(' > ');
  const baseLabel = `[worker:${testInfo.workerIndex}] [project:${testInfo.project.name}] [test:${testId}]`;
  metadata.stream.write(`[${new Date().toISOString()}] ${baseLabel} END_BROWSER_CONSOLE\n`);
  metadata.stream.end();
  logMetadata.delete(page);
});

test('parameter selection updates the application state', async ({ page }) => {
  const selectedParameter = page.getByTestId('selected-parameter');
  await expect(selectedParameter).toHaveText('LZeq');

  const select = page.getByTestId('parameter-select');
  await select.selectOption('LCeq');

  await expect(selectedParameter).toHaveText('LCeq');
  await expect(page.getByTestId('view-mode')).toHaveText('overview');
});

test('view toggle switches between log and overview modes', async ({ page }) => {
  const toggle = page.getByTestId('view-toggle');
  const viewMode = page.getByTestId('view-mode');

  await expect(toggle).toHaveText('Log View Disabled');
  await expect(viewMode).toHaveText('overview');

  await toggle.click();
  await expect(viewMode).toHaveText('log');
  await expect(toggle).toHaveText('Log View Enabled');

  await toggle.click();
  await expect(viewMode).toHaveText('overview');
  await expect(toggle).toHaveText('Log View Disabled');
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

test('users can switch between regions and markers tabs', async ({ page }) => {
  const markersPanel = page.getByTestId('markers-panel');
  await expect(markersPanel).toBeHidden();

  await page.getByTestId('tab-markers').click();
  await expect(markersPanel).toBeVisible();

  await page.getByTestId('tab-regions').click();
  await expect(markersPanel).toBeHidden();
});

test('user can create a marker with the keyboard and view details', async ({ page }) => {
  const chart = page.getByTestId('chart');
  const markerCount = page.getByTestId('marker-count');
  const markerList = page.getByTestId('marker-list');

  const box = await chart.boundingBox();
  if (!box) {
    throw new Error('Unable to determine chart bounding box for marker test.');
  }

  await chart.click({ position: { x: box.width * 0.3, y: box.height / 2 } });
  await page.keyboard.press('m');

  await page.getByTestId('tab-markers').click();
  await expect(markerCount).toHaveText('1');

  const markerEntry = markerList.locator('.marker-entry').first();
  await expect(markerEntry).toHaveCount(1);
  await markerEntry.click();

  const markerDetail = page.getByTestId('marker-detail');
  await expect(markerDetail).toContainText('Marker 1');
});

test('user can create a region using the R key workflow', async ({ page }) => {
  const chart = page.getByTestId('chart');
  const regionCount = page.getByTestId('region-count');

  const box = await chart.boundingBox();
  if (!box) {
    throw new Error('Unable to determine chart bounding box for R-key test.');
  }

  await chart.click({ position: { x: box.width * 0.2, y: box.height / 2 } });
  await page.keyboard.press('m');

  await chart.click({ position: { x: box.width * 0.7, y: box.height / 2 } });
  await page.keyboard.press('m');

  await page.keyboard.press('r');

  await expect(regionCount).toHaveText('1');
});

test('auto day & night regions button creates regions', async ({ page }) => {
  // Add the auto day/night button to the harness
  await page.evaluate(() => {
    const button = document.createElement('button');
    button.setAttribute('data-testid', 'auto-daynight-button');
    button.textContent = 'Auto Day & Night';
    button.addEventListener('click', () => {
      const handlers = (window as any).NoiseSurveyApp?.eventHandlers;
      if (typeof handlers?.handleAutoRegions === 'function') {
        handlers.handleAutoRegions();
      }
    });
    document.querySelector('.control-panel')?.appendChild(button);
  });

  const autoDayNightButton = page.getByTestId('auto-daynight-button');
  const regionCount = page.getByTestId('region-count');

  await expect(regionCount).toHaveText('0');
  await autoDayNightButton.click();

  // Wait a bit for async operations
  await page.waitForTimeout(500);

  // Check if regions were created (should be at least 2: one daytime, one nighttime for P1)
  const count = await regionCount.textContent();
  expect(parseInt(count || '0')).toBeGreaterThan(0);
});
