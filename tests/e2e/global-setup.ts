import fs from 'node:fs';
import path from 'node:path';
import type { FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
  const configDir = config.configDir ?? process.cwd();
  const logFilePath = path.resolve(configDir, 'playwright-console.log');
  fs.writeFileSync(logFilePath, '', 'utf-8');
}

export default globalSetup;
