import { defineConfig } from '@playwright/test'

// Roda contra uma stack de verdade (compose) — BASE_URL aponta para o nginx.
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8090',
    screenshot: 'only-on-failure',
  },
})
