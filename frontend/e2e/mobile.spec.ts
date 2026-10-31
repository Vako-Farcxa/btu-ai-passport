import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

import { hydrated } from './helpers'

const API = 'http://localhost:8000'

// A phone: 390 px is where the brand text next to the logo is hidden by CSS.
test.use({ locale: 'en-US', viewport: { width: 390, height: 844 } })

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
  test(`${path} at 390 px: no serious accessibility violations, named logo link, no sideways scroll`, async ({
    page,
  }) => {
    await page.goto(path)
    await hydrated(page.locator('main'))
    expect(await violations(page)).toEqual([])

    // The brand text is not shown on a phone, but the logo link must keep its name.
    const word = await page.locator('.brand-word').boundingBox()
    expect(word?.width ?? 0).toBeLessThanOrEqual(1)
    const logo = page.getByRole('link', {
      name: 'Business and Technology University',
    })
    await expect(logo).toHaveAttribute('href', '/')
    await expect(logo).toBeVisible()

    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })
}

test('a verify result at 390 px has no serious accessibility violations', async ({
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
  const input = page.getByLabel('Verification code')
  await hydrated(input)
  await input.fill('A1B2-C3D4-E5F6-G7H8')
  await page.getByRole('button', { name: 'Check' }).click()
  await expect(page.getByTestId('verify-result')).toContainText('Valid')
  expect(await violations(page)).toEqual([])
  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
})

test('the admin activity page at 390 px has no serious accessibility violations', async ({
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
