import { expect, test } from '@playwright/test'

const CODE = 'A1B2-C3D4-E5F6-G7H8'
const ME = 'http://localhost:8000/me/passport'

test.use({ locale: 'en-US' })

test('a shared verify link prefills and checks the code once', async ({
  page,
}) => {
  const sent: string[] = []
  await page.route('http://localhost:8000/verify', async (route) => {
    const body = route.request().postDataJSON() as { code: string }
    sent.push(body.code)
    await route.fulfill({
      json: {
        outcome: 'valid',
        holder_name: 'Nino Beridze',
        version: 2,
        is_latest: true,
        skills: [
          { skill: 'Machine Learning', badge: 'BDG-AI-001', awarded_on: null },
        ],
        tx_url: 'https://amoy.polygonscan.com/tx/0x' + '11'.repeat(32),
      },
    })
  })
  await page.goto(`/verify?code=${CODE.toLowerCase()}`)
  await expect(page.getByLabel('Verification code')).toHaveValue(CODE)
  await expect(page.getByTestId('verify-result')).toContainText('Valid')
  await expect(page.getByTestId('verify-result')).toContainText('Nino Beridze')
  expect(sent).toEqual([CODE])
})

test('the verify page without a code does not call the API', async ({
  page,
}) => {
  let calls = 0
  await page.route('http://localhost:8000/verify', async (route) => {
    calls += 1
    await route.fulfill({ json: { outcome: 'not_found' } })
  })
  await page.goto('/verify')
  await expect(page.getByLabel('Verification code')).toHaveValue('')
  await expect(page.getByTestId('verify-result')).toHaveCount(0)
  expect(calls).toBe(0)
})

test('a student copies a share link for a version', async ({
  page,
  context,
  baseURL,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await context.addCookies([
    {
      name: 'passport_mock_bearer',
      value: 'test-token',
      url: baseURL!,
    },
  ])
  await page.route(ME, async (route) => {
    await route.fulfill({
      json: {
        passport: {
          passport_id: 'BTU-A1B2C3D4E5',
          versions: [
            {
              version: 2,
              issued_at: '2025-06-01T00:00:00Z',
              is_current: true,
              holder_name: 'Nino Beridze',
              verification_code: CODE,
              skills: [],
              anchor: { status: 'pending', tx_url: null },
            },
          ],
        },
      },
    })
  })
  await page.goto('/passport')
  await page.getByRole('button', { name: 'Copy share link' }).click()
  await expect(page.getByText('Share link copied')).toBeVisible()
  const text = await page.evaluate(() => navigator.clipboard.readText())
  expect(text).toBe(`${baseURL}/verify?code=${CODE}`)

  await page.getByRole('button', { name: 'ქართული' }).click()
  await expect(
    page.getByRole('button', { name: 'ბმულის კოპირება' }),
  ).toBeVisible()
})
