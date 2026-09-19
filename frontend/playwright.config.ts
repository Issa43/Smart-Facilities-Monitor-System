import { defineConfig, devices } from '@playwright/test'

const frontendUrl = process.env.E2E_FRONTEND_URL ?? 'http://127.0.0.1:4173'
const apiUrl = process.env.E2E_API_URL ?? 'http://127.0.0.1:18000/api/v1'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 8_000 },
  use: {
    baseURL: frontendUrl,
    locale: 'ar-EG',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        channel: process.env.PLAYWRIGHT_CHANNEL ?? 'chrome',
      },
    },
  ],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 4173',
    url: frontendUrl,
    reuseExistingServer: false,
    env: { VITE_API_BASE_URL: apiUrl },
    timeout: 120_000,
  },
})
