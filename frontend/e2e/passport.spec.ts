import { expect, test } from '@playwright/test'

const API = 'http://localhost:8000/me/passport'
const OWN_ID = 'BTU-A1B2C3D4E5'
const OTHER_ID = 'BTU-V2W3X4Y5Z6'
const OTHER_CODE = 'V2W3-X4Y5-Z6A7-B8C9'

const caller = {
  passport: {
    passport_id: OWN_ID,
    versions: [
      {
        version: 2,
        issued_at: '2025-06-01T00:00:00Z',
        is_current: true,
        holder_name: 'Nino Beridze',
        verification_code: 'A1B2-C3D4-E5F6-G7H8',
        skills: [
          {
            skill: 'Machine Learning',
            badge: 'Stamp',
            awarded_on: '2025-06-01',
          },
        ],
        anchor: {
          status: 'confirmed',
          tx_url: 'https://amoy.polygonscan.com/tx/0x' + '11'.repeat(32),
        },
      },
      {
        version: 1,
        issued_at: '2025-01-15T00:00:00Z',
        is_current: false,
        holder_name: 'Nino Beridze',
        verification_code: 'K9M2-N3P4-Q5R6-S7T8',
        skills: [
          { skill: 'Python', badge: 'Foundation', awarded_on: '2025-01-15' },
        ],
        anchor: {
          status: 'confirmed',
          tx_url: 'https://amoy.polygonscan.com/tx/0x' + '22'.repeat(32),
        },
      },
    ],
  },
}

test.use({ locale: 'en-US' })

test.beforeEach(async ({ context }) => {
  await context.addCookies([
    {
      name: 'passport_mock_bearer',
      value: 'test-token',
      url: 'http://localhost:3000',
    },
  ])
})

test('a student with no row sees an empty passport', async ({ page }) => {
  await page.route(API, async (route) => {
    expect(route.request().headers().authorization).toBe('Bearer test-token')
    await route.fulfill({ json: { passport: null } })
  })
  await page.goto('/passport')
  await expect(page.getByRole('status')).toHaveText(
    'No passport is available yet.',
  )
  await expect(page.getByText(/BTU-/)).toHaveCount(0)
  await expect(page.getByRole('button', { name: /download/i })).toHaveCount(0)
})

test('a non-BTU session is refused and sees no passport', async ({ page }) => {
  await page.route(API, async (route) => {
    await route.fulfill({
      status: 403,
      json: { code: 'domain_not_allowed' },
    })
  })
  await page.goto('/')
  await expect(
    page.getByRole('alert').filter({ hasText: 'btu.edu.ge' }),
  ).toBeVisible()
  await expect(page.getByRole('link', { name: 'Verify a code' })).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Sign in with Google' }),
  ).toBeVisible()
  await expect(page.getByText(OWN_ID)).toHaveCount(0)

  await page.goto('/passport')
  await expect(
    page.getByRole('alert').filter({ hasText: 'btu.edu.ge' }),
  ).toBeVisible()
  await expect(page.getByText('A1B2-C3D4-E5F6-G7H8')).toHaveCount(0)
  await expect(page.getByText(OTHER_ID)).toHaveCount(0)
})

test('a signed-in student cannot open another passport', async ({ page }) => {
  await page.route(API, async (route) => {
    expect(route.request().headers().authorization).toBe('Bearer test-token')
    await route.fulfill({ json: caller })
  })
  await page.goto(`/passport?passport_id=${OTHER_ID}`)
  await expect(page.getByText(OWN_ID)).toBeVisible()
  await expect(page.getByText('A1B2-C3D4-E5F6-G7H8')).toBeVisible()
  await expect(page.getByText('K9M2-N3P4-Q5R6-S7T8')).toBeVisible()
  await expect(page.getByText('Machine Learning')).toBeVisible()
  await expect(page.getByText(OTHER_ID)).toHaveCount(0)
  await expect(page.getByText(OTHER_CODE)).toHaveCount(0)
  await expect(page.getByRole('button', { name: /download/i })).toHaveCount(0)

  await page.getByRole('button', { name: 'ქართული' }).click()
  await expect(page.getByText('პასპორტის ID')).toBeVisible()
  await expect(page.getByText('Machine Learning')).toBeVisible()

  await page.goto(`/passport/${OTHER_ID}`)
  await expect(page.getByText(OTHER_CODE)).toHaveCount(0)
  await expect(page.getByText('Nino Beridze')).toHaveCount(0)
})
