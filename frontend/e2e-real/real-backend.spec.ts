import { expect, test, type Page } from '@playwright/test'

// Codes seeded by backend/scripts/serve_e2e.py. All names and data are fictional.
const VALID = 'A1B2-C3D4-E5F6-G7H8'
const OUTDATED = 'K9M2-N3P4-Q5R6-S7T8'
const PENDING = 'V2W3-X4Y5-Z6A7-B8C9'
const REVOKED = 'R3V0-K3D0-0000-0001'
const TAMPERED = 'T4MP-3RED-0000-0002'
const CHAIN_MISMATCH = 'C4A1-N0FF-0000-0003'

/** Types a code, submits it and returns the real API answer the page received. */
async function verify(page: Page, code: string) {
  const input = page.getByLabel('Verification code')
  await expect
    .poll(() =>
      input.evaluate((node) =>
        Object.keys(node).some((key) => key.startsWith('__reactProps')),
      ),
    )
    .toBe(true)
  await input.fill(code)
  const answered = page.waitForResponse(
    (response) =>
      response.url().endsWith('/verify') &&
      response.request().method() === 'POST',
  )
  await input.press('Enter')
  const response = await answered
  expect(response.status()).toBe(200)
  return (await response.json()) as Record<string, unknown>
}

// Nothing in these specs is mocked, so a request that never reaches the servers is a failure.
const failed: string[] = []
test.beforeEach(({ page }) => {
  failed.length = 0
  page.on('requestfailed', (request) => {
    if (!request.url().includes('_rsc=')) failed.push(request.url())
  })
})
test.afterEach(() => {
  expect(failed).toEqual([])
})

test('a valid code shows the holder, the skills and a verified on-chain badge', async ({
  page,
}) => {
  await page.goto('/verify')
  const body = await verify(page, VALID)
  expect(body).toMatchObject({
    outcome: 'valid',
    holder_name: 'Nino Beridze',
    version: 2,
    is_latest: true,
  })

  const result = page.getByTestId('verify-result')
  await expect(result).toContainText('Valid')
  await expect(result).toContainText('Nino Beridze')
  await expect(result).toContainText('Machine Learning')
  await expect(result).toContainText('This is the latest version')
  await expect(page.getByTestId('newer-notice')).toHaveCount(0)
  const badge = page.getByTestId('onchain-badge')
  await expect(badge).toHaveAttribute('data-status', 'verified')
  await expect(badge).toContainText('Verified on-chain, block 4242')
  // The result never shows the private fields of the passport.
  await expect(result).not.toContainText('demo.student@btu.edu.ge')
  await expect(result).not.toContainText('BTU-A1B2C3D4E5')
})

test('an older version is outdated and points to the newer one, without its code', async ({
  page,
}) => {
  await page.goto(`/verify?code=${OUTDATED}`)
  const result = page.getByTestId('verify-result')
  await expect(result).toContainText('Outdated version')
  await expect(result).toContainText('Python')
  await expect(page.getByTestId('newer-notice')).toContainText('v2')
  await expect(page.getByTestId('onchain-badge')).toHaveAttribute(
    'data-status',
    'verified',
  )
  await expect(page.locator('body')).not.toContainText(VALID)
})

test('an unknown or badly formed code says not found, and an empty one asks for a code', async ({
  page,
}) => {
  await page.goto('/verify')
  const body = await verify(page, 'ZZZZ-ZZZZ-ZZZZ-ZZZZ')
  expect(body).toEqual({ outcome: 'not_found' })
  await expect(page.getByTestId('verify-result')).toContainText('Not found')
  await expect(page.getByTestId('not-found-notice')).toContainText(
    'Check it for typing mistakes',
  )
  await expect(page.getByTestId('verify-result')).not.toContainText('Nino')

  // A code with lower case and spaces around it is accepted the same way as the stored one.
  const again = await verify(page, `  ${VALID.toLowerCase()}  `)
  expect(again.outcome).toBe('valid')

  // Empty input never reaches the API: the page asks for a code.
  await page.getByLabel('Verification code').fill('   ')
  await page.getByRole('button', { name: 'Check' }).click()
  await expect(page.locator('#code-hint')).toHaveText(
    'Enter a verification code',
  )
})

test('revoked, tampered and pending records show no name and no skills', async ({
  page,
}) => {
  await page.goto('/verify')

  expect((await verify(page, REVOKED)).outcome).toBe('revoked')
  const result = page.getByTestId('verify-result')
  await expect(page.getByTestId('revoked-notice')).toContainText('revoked')
  await expect(result).not.toContainText('Revoked Student')
  await expect(result).not.toContainText('Prompt Engineering')

  // The stored name was changed after it was hashed: caught by the database check.
  const edited = await verify(page, TAMPERED)
  expect(edited).toMatchObject({
    outcome: 'tampered',
    reason: 'stored_content_changed',
  })
  await expect(page.getByTestId('tampered-notice')).toBeVisible()
  await expect(result).not.toContainText('Someone Else')
  await expect(result).not.toContainText('Original Name')

  // The contract holds a different hash than the database: caught by the chain check.
  const mismatch = await verify(page, CHAIN_MISMATCH)
  expect(mismatch).toMatchObject({
    outcome: 'tampered',
    reason: 'chain_mismatch',
  })
  await expect(page.getByTestId('tampered-notice')).toBeVisible()
  await expect(result).not.toContainText('Chain Mismatch')

  expect((await verify(page, PENDING)).outcome).toBe('pending')
  await expect(page.getByTestId('pending-notice')).toBeVisible()
  await expect(result).not.toContainText('Giorgi Kapanadze')
})

test('the admin area asks the real API who you are: a stranger is stopped, the demo admin gets in', async ({
  page,
  context,
  baseURL,
}) => {
  // No session: the gate shows the sign-in screen and nothing from the panel.
  await page.goto('/admin')
  await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
  await expect(
    page.getByRole('navigation', { name: 'Admin Navigation' }),
  ).toHaveCount(0)

  // A session the API does not accept (it needs a real Supabase login) is turned away.
  await context.addCookies([
    { name: 'passport_mock_bearer', value: 'not-a-real-token', url: baseURL! },
  ])
  await page.goto('/admin')
  await expect(
    page.getByRole('navigation', { name: 'Admin Navigation' }),
  ).toHaveCount(0)

  // The backend runs in demo mode, which accepts the "demo-admin" token and answers
  // /admin/me with the demo admin's email: the page shows what the API said.
  await context.addCookies([
    { name: 'passport_mock_bearer', value: 'demo-admin', url: baseURL! },
  ])
  const me = page.waitForResponse(
    (response) =>
      response.url().endsWith('/admin/me') &&
      response.request().headers()['authorization'] === 'Bearer demo-admin',
  )
  await page.goto('/admin')
  expect((await me).status()).toBe(200)
  await expect(
    page.getByRole('navigation', { name: 'Admin Navigation' }),
  ).toBeVisible()
  await expect(page.getByText('admin@btu.edu.ge').first()).toBeVisible()
})
