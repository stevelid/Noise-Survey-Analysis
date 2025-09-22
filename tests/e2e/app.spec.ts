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
  const testId = testInfo.titlePath().join(' > ');
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
  const testId = testInfo.titlePath().join(' > ');
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
