import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  reporter: [['list']],
  globalSetup: './tests/e2e/global-setup.ts',
  use: {
    headless: true,
  },
});
