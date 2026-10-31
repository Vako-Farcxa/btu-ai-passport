import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

import { hydrated } from './helpers'

const API = 'http://localhost:8000'

test.use({ locale: 'en-US' })

/** Serious and critical WCAG A and AA violations, with the nodes that caused them. */
async function violations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  return results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => ({
      id: v.id,
      impact: v.impact,
      nodes: v.nodes.map((n) => n.target.join(' ')),
    }))
}

for (const path of ['/', '/verify', '/about', '/privacy', '/terms']) {
  test(`${path} has no serious accessibility violations`, async ({ page }) => {
    await page.goto(path)
    await hydrated(page.locator('main'))
    expect(await violations(page)).toEqual([])
  })
}

test('a verify result has no serious accessibility violations', async ({
  page,
}) => {
  await page.route(`${API}/verify`, (route) =>
    route.fulfill({
      json: {
        outcome: 'valid',
        holder_name: 'Nino Beridze',
        version: 1,
        is_latest: true,
        skills: [
          {
            skill: 'Machine Learning',
            badge: 'BDG-AI-002',
            awarded_on: '2026-06-01',
            description: 'Choose a model the decision can survive.',
          },
        ],
        tx_url: 'https://amoy.polygonscan.com/tx/0x' + '11'.repeat(32),
      },
    }),
  )
  await page.goto('/verify')
  await hydrated(page.getByLabel('Verification code'))
  await page.getByLabel('Verification code').fill('A1B2-C3D4-E5F6-G7H8')
  await page.getByRole('button', { name: 'Check' }).click()
  await expect(page.getByTestId('verify-result')).toContainText('Valid')
  expect(await violations(page)).toEqual([])
})

test('the admin activity page has no serious accessibility violations', async ({
  page,
  context,
  baseURL,
}) => {
  await context.addCookies([
    { name: 'passport_mock_bearer', value: 'test-token', url: baseURL! },
  ])
  await page.route(`${API}/admin/me`, (route) =>
    route.fulfill({ json: { email: 'admin@btu.edu.ge' } }),
  )
  await page.route(`${API}/admin/audit**`, (route) =>
    route.fulfill({
      json: {
        entries: [
          {
            id: 'a1',
            created_at: '2026-10-31T10:00:00Z',
            actor: 'admin@btu.edu.ge',
            action: 'sync.run',
            target_type: 'sync',
            target: 'manual',
            detail: {},
          },
        ],
      },
    }),
  )
  await page.goto('/admin/audit')
  await expect(page.getByText('Ran a sync')).toBeVisible()
  expect(await violations(page)).toEqual([])
})

test('the student passport page and the flag dialog have no serious violations', async ({
  page,
  context,
  baseURL,
}) => {
  await context.addCookies([
    { name: 'passport_mock_bearer', value: 'test-token', url: baseURL! },
  ])
  await page.route(`${API}/me/passport`, (route) =>
    route.fulfill({
      json: {
        passport: {
          passport_id: 'BTU-A1B2C3D4E5',
          versions: [
            {
              version: 1,
              issued_at: '2026-10-01T00:00:00Z',
              is_current: true,
              holder_name: 'Nino Beridze',
              verification_code: 'A1B2-C3D4-E5F6-G7H8',
              skills: [],
              anchor: {
                status: 'confirmed',
                tx_url: 'https://amoy.polygonscan.com/tx/0x' + '11'.repeat(32),
              },
            },
          ],
        },
      },
    }),
  )
  await page.route(`${API}/me/flags`, (route) =>
    route.fulfill({ json: { flags: [], unread: 0 } }),
  )
  await page.goto('/passport')
  const flag = page.getByRole('button', { name: 'Flag an issue' })
  await hydrated(flag)
  expect(await violations(page)).toEqual([])
  await flag.click()
  await expect(page.getByRole('dialog')).toBeVisible()
  expect(await violations(page)).toEqual([])
})

test('the admin students page with the add dialog has no serious violations', async ({
  page,
  context,
  baseURL,
}) => {
  await context.addCookies([
    { name: 'passport_mock_bearer', value: 'test-token', url: baseURL! },
  ])
  await page.route(`${API}/admin/me`, (route) =>
    route.fulfill({ json: { email: 'admin@btu.edu.ge' } }),
  )
  await page.route(`${API}/admin/students**`, (route) =>
    route.fulfill({ json: { students: [], total: 0 } }),
  )
  await page.route(`${API}/admin/skills`, (route) =>
    route.fulfill({ json: { skills: [] } }),
  )
  await page.goto('/admin/students')
  const add = page.getByRole('button', { name: 'Add student' })
  await hydrated(add)
  expect(await violations(page)).toEqual([])
  await add.click()
  await expect(page.getByRole('dialog')).toBeVisible()
  expect(await violations(page)).toEqual([])
})

test('the admin flags page has no serious violations', async ({
  page,
  context,
  baseURL,
}) => {
  await context.addCookies([
    { name: 'passport_mock_bearer', value: 'test-token', url: baseURL! },
  ])
  await page.route(`${API}/admin/me`, (route) =>
    route.fulfill({ json: { email: 'admin@btu.edu.ge' } }),
  )
  await page.route(`${API}/admin/flags**`, (route) =>
    route.fulfill({
      json: {
        open_count: 1,
        flags: [
          {
            id: 'f1',
            passport_id: 'BTU-A1B2C3D4E5',
            version: 1,
            verification_code: 'A1B2-C3D4-E5F6-G7H8',
            student_email: 'nino.beridze@btu.edu.ge',
            comment: 'The Python skill is missing from this version.',
            status: 'open',
            admin_note: '',
            resolved_by: null,
            created_at: '2026-10-31T10:00:00Z',
            resolved_at: null,
          },
        ],
      },
    }),
  )
  await page.goto('/admin/flags')
  await expect(page.getByText('The Python skill is missing')).toBeVisible()
  expect(await violations(page)).toEqual([])
})
