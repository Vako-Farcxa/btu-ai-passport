import { defineConfig } from '@playwright/test'

// Locally the specs run against `next dev`. In CI (CI=true) they run against the production
// build, so the workflow runs `npm run build` first (with the same NEXT_PUBLIC_* values as
// the env below, because Next.js inlines them at build time) and this starts `next start`.
const isCI = Boolean(process.env.CI)
const port = Number(process.env.E2E_PORT ?? 3000)
const baseURL = `http://localhost:${port}`

export default defineConfig({
  testDir: './e2e',
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  reporter: isCI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: { baseURL, trace: 'retain-on-failure' },
  webServer: {
    command: isCI
      ? `npm run start -- --port ${port}`
      : `npm run dev -- --port ${port}`,
    url: baseURL,
    reuseExistingServer: !isCI,
    env: {
      NEXT_PUBLIC_API_URL: 'http://localhost:8000',
      NEXT_PUBLIC_AUTH_MOCK: '1',
      NEXT_PUBLIC_SUPABASE_URL: 'http://127.0.0.1:54321',
      NEXT_PUBLIC_SUPABASE_ANON_KEY: 'mock-anon-key',
    },
  },
})
