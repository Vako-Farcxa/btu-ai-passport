import { expect, test, type Page } from '@playwright/test'

const API = 'http://localhost:8000'

test.use({ locale: 'en-US' })

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: 'passport_mock_bearer', value: 'test-token', url: baseURL! },
  ])
})

/** Everything the dashboard asks for, with only the health answer changing per test. */
async function mockDashboard(page: Page, health: object | { status: number }) {
  await page.route(`${API}/admin/me`, (route) =>
    route.fulfill({ json: { email: 'admin@btu.edu.ge' } }),
  )
  await page.route(`${API}/admin/students**`, (route) =>
    route.fulfill({ json: { students: [], total: 0 } }),
  )
  await page.route(`${API}/admin/versions/pending`, (route) =>
    route.fulfill({ json: { versions: [] } }),
  )
  await page.route(`${API}/admin/sync-runs**`, (route) =>
    route.fulfill({ json: { runs: [] } }),
  )
  await page.route(`${API}/admin/flags**`, (route) =>
    route.fulfill({ json: { flags: [], open_count: 0 } }),
  )
  await page.route(`${API}/admin/health`, async (route) => {
    expect(route.request().headers().authorization).toBe('Bearer test-token')
    if ('status' in health && typeof health.status === 'number') {
      await route.fulfill({ status: health.status, json: { code: 'x' } })
    } else {
      await route.fulfill({ json: health })
    }
  })
}

const base = {
  checked_at: '2026-10-31T12:00:00Z',
  last_sync_status: 'failed',
  last_sync_error: 'sheet_unavailable',
  last_sync_at: '2026-10-31T11:58:00Z',
  last_success_at: '2026-10-31T11:00:00Z',
  anchors_failed_permanent: 0,
  anchors_stuck: 0,
  inconsistencies: 0,
}

test('a failed sync shows a red banner with its reason', async ({ page }) => {
  await mockDashboard(page, {
    ...base,
    status: 'critical',
    alerts: [
      {
        code: 'sync_failed',
        severity: 'critical',
        message: 'The last sync failed.',
        reason: 'sheet_unavailable',
        count: null,
      },
    ],
  })
  await page.goto('/admin')
  const banner = page.getByTestId('health-banner')
  await expect(banner).toBeVisible()
  await expect(banner).toHaveAttribute('data-severity', 'critical')
  await expect(banner).toContainText('The last sync failed.')
  await expect(banner).toContainText('sheet_unavailable')
  await expect(
    banner.getByRole('link', { name: 'Open Sync Monitor' }),
  ).toHaveAttribute('href', '/admin/sync')
})

test('only warnings show an amber banner', async ({ page }) => {
  await mockDashboard(page, {
    ...base,
    status: 'warning',
    alerts: [
      {
        code: 'sync_stale',
        severity: 'warning',
        message:
          'No sync has completed for 75 minutes. It should run every 15 minutes.',
        reason: null,
        count: null,
      },
    ],
  })
  await page.goto('/admin')
  const banner = page.getByTestId('health-banner')
  await expect(banner).toHaveAttribute('data-severity', 'warning')
  await expect(banner).toContainText('75 minutes')
})

test('no banner when everything is fine', async ({ page }) => {
  await mockDashboard(page, { ...base, status: 'ok', alerts: [] })
  await page.goto('/admin')
  await expect(
    page.getByRole('heading', { name: 'System Dashboard' }),
  ).toBeVisible()
  await expect(page.getByTestId('health-banner')).toHaveCount(0)
})

test('an unreachable health check says so instead of staying silent', async ({
  page,
}) => {
  await mockDashboard(page, { status: 503 })
  await page.goto('/admin')
  await expect(page.getByTestId('health-banner')).toContainText(
    'System health could not be checked.',
  )
})
