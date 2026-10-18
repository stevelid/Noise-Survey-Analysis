import fs from 'node:fs';
import path from 'node:path';
import type { FullConfig } from '@playwright/test';
import { execFileSync } from 'node:child_process';

async function globalSetup(config: FullConfig) {
  const configDir = config.configDir ?? process.cwd();
  const logFilePath = path.resolve(configDir, 'playwright-console.log');
  fs.writeFileSync(logFilePath, '', 'utf-8');
  execFileSync('python', ['tests/e2e/build_dashboard.py'], { cwd: configDir, stdio: 'pipe' });
}

export default globalSetup;
