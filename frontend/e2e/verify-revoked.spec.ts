import { expect, test } from '@playwright/test'

import { hydrated } from './helpers'

const REVOKED = 'R1R2-R3R4-R5R6-R7R8'

test.use({ locale: 'en-US' })

test('a revoked passport is shown as revoked with the date and shows no skills', async ({
  page,
}) => {
  await page.route('http://localhost:8000/verify', async (route) => {
    await route.fulfill({
      json: { outcome: 'revoked', revoked_at: '2026-10-30T10:00:00+00:00' },
    })
  })
  await page.goto('/verify')
  await hydrated(page.getByLabel('Verification code'))
  await page.getByLabel('Verification code').fill(REVOKED)
  await page.getByRole('button', { name: 'Check' }).click()

  const result = page.getByTestId('verify-result')
  await expect(result).toHaveAttribute('aria-label', 'Revoked')
  await expect(result).toHaveClass(/outcome-revoked/)
  await expect(page.getByTestId('revoked-notice')).toContainText(
    'was revoked on 30 Oct 2026',
  )
  // Nothing that could be mistaken for a valid passport.
  await expect(result).not.toContainText('Valid')
  await expect(result.locator('.holder')).toHaveCount(0)
  await expect(result.locator('.badge-stamp')).toHaveCount(0)
  await expect(result.getByRole('link')).toHaveCount(0)
})

test('the revoked notice is Georgian in Georgian', async ({ page }) => {
  await page.route('http://localhost:8000/verify', async (route) => {
    await route.fulfill({
      json: { outcome: 'revoked', revoked_at: '2026-10-30T10:00:00+00:00' },
    })
  })
  await page.goto('/verify')
  await hydrated(page.getByLabel('Verification code'))
  await page.getByRole('button', { name: 'ქართული' }).click()
  await page.getByLabel('შემოწმების კოდი').fill(REVOKED)
  await page.getByRole('button', { name: 'შემოწმება' }).click()
  await expect(page.getByTestId('revoked-notice')).toContainText('30 ოქტ. 2026')
})

test('a code that matches nobody says what to try, in both languages', async ({
  page,
}) => {
  await page.route('http://localhost:8000/verify', async (route) => {
    await route.fulfill({ json: { outcome: 'not_found' } })
  })
  await page.goto('/verify')
  await hydrated(page.getByLabel('Verification code'))
  await page.getByLabel('Verification code').fill('NOPE-NOPE-NOPE-NOPE')
  await page.getByRole('button', { name: 'Check' }).click()
  await expect(page.getByTestId('not-found-notice')).toContainText(
    'ask the holder to copy it again',
  )
  await page.getByRole('button', { name: 'ქართული' }).click()
  await expect(page.getByTestId('not-found-notice')).toContainText('ტირეებით')
})
