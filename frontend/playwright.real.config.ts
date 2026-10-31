import { defineConfig } from '@playwright/test'

// Browser tests with NOTHING mocked: a real browser, the real Next.js app and the real
// FastAPI backend (backend/scripts/serve_e2e.py, seeded fixture data, no secrets). They are
// the check that the front end and the back end still agree, which the mocked specs in
// e2e/ cannot give.
//
//   npm run build   (with the NEXT_PUBLIC_* values below)
//   npm run e2e:real
//
// Locally the front end runs as `next dev`. With CI=true it runs the production build.
const isCI = Boolean(process.env.CI)
const frontendPort = Number(process.env.E2E_PORT ?? 3000)
const backendPort = Number(process.env.E2E_BACKEND_PORT ?? 8000)
const baseURL = `http://localhost:${frontendPort}`

export default defineConfig({
  testDir: './e2e-real',
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  workers: 1,
  reporter: isCI ? [['list'], ['html', { open: 'never' }]] : 'list',
  outputDir: 'test-results-real',
  use: { baseURL, trace: 'retain-on-failure', locale: 'en-US' },
  webServer: [
    {
      // The API with fixture data. It refuses to start if a real service is configured.
      command: 'uv run python scripts/serve_e2e.py',
      cwd: '../backend',
      url: `http://127.0.0.1:${backendPort}/health`,
      reuseExistingServer: !isCI,
      timeout: 120_000,
      env: { E2E_BACKEND_PORT: String(backendPort) },
    },
    {
      command: isCI
        ? `npm run start -- --port ${frontendPort}`
        : `npm run dev -- --port ${frontendPort}`,
      url: baseURL,
      reuseExistingServer: !isCI,
      timeout: 120_000,
      env: {
        NEXT_PUBLIC_API_URL: `http://localhost:${backendPort}`,
        NEXT_PUBLIC_AUTH_MOCK: '1',
        NEXT_PUBLIC_SUPABASE_URL: 'http://127.0.0.1:54321',
        NEXT_PUBLIC_SUPABASE_ANON_KEY: 'mock-anon-key',
      },
    },
  ],
})
