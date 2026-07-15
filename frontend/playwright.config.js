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
    // Câmera falsa do Chromium (vídeo sintético) + permissão concedida:
    // testa a câmera guiada sem hardware — inclusive no CI.
    permissions: ['camera'],
    launchOptions: {
      args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
    },
  },
})
