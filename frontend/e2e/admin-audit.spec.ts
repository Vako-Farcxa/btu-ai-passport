import { expect, test } from '@playwright/test'

const API = 'http://localhost:8000'

test.use({ locale: 'en-US' })

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: 'passport_mock_bearer', value: 'test-token', url: baseURL! },
  ])
})

test('the activity page lists admin changes and is in the admin menu', async ({
  page,
}) => {
  await page.route(`${API}/admin/me`, (route) =>
    route.fulfill({ json: { email: 'admin@btu.edu.ge' } }),
  )
  await page.route(`${API}/admin/audit**`, async (route) => {
    expect(route.request().headers().authorization).toBe('Bearer test-token')
    await route.fulfill({
      json: {
        entries: [
          {
            id: 'a1',
            created_at: '2026-10-31T10:00:00Z',
            actor: 'admin@btu.edu.ge',
            action: 'version.revoke',
            target_type: 'version',
            target: 'v-123',
            detail: { passport_id: 'BTU-ABC', version: 2 },
          },
        ],
      },
    })
  })

  await page.goto('/admin/audit')
  await expect(page.getByRole('heading', { name: 'Activity' })).toBeVisible()
  const row = page.getByRole('row', { name: /Revoked a version/ })
  await expect(row).toContainText('admin@btu.edu.ge')
  await expect(row).toContainText('v-123')
  await expect(row).toContainText('passport id: BTU-ABC, version: 2')
  await expect(
    page
      .getByRole('navigation', { name: 'Admin Navigation' })
      .getByRole('link', { name: 'Activity' }),
  ).toHaveAttribute('href', '/admin/audit')
})
