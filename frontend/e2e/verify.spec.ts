import { expect, test } from '@playwright/test'

const VALID = 'A1B2-C3D4-E5F6-G7H8'
const OUTDATED = 'K9M2-N3P4-Q5R6-S7T8'
const PENDING = 'V2W3-X4Y5-Z6A7-B8C9'

test('verification page shows one still outcome', async ({ page }) => {
  let calls = 0
  await page.route('http://localhost:8000/verify', async (route) => {
    calls += 1
    const body = route.request().postDataJSON() as { code: string }
    const code = body.code.trim().toUpperCase()
    if (code === VALID) {
      await route.fulfill({
        json: {
          outcome: 'valid',
          holder_name: 'Nino Beridze',
          version: 2,
          is_latest: true,
          skills: [
            {
              skill: 'Machine Learning',
              badge: 'Stamp',
              awarded_on: '2025-06-01',
            },
          ],
          tx_url: 'https://amoy.polygonscan.com/tx/0x' + '11'.repeat(32),
        },
      })
      return
    }
    if (code === OUTDATED) {
      await route.fulfill({
        json: {
          outcome: 'outdated',
          holder_name: 'Nino Beridze',
          version: 1,
          is_latest: false,
          skills: [
            { skill: 'Python', badge: 'Foundation', awarded_on: '2025-01-15' },
          ],
          tx_url: 'https://amoy.polygonscan.com/tx/0x' + '22'.repeat(32),
        },
      })
      return
    }
    if (code === PENDING) {
      await route.fulfill({ json: { outcome: 'error' } })
      return
    }
    await route.fulfill({ json: { outcome: 'not_found' } })
  })
  await page.goto('/verify')

  await page.getByRole('button', { name: 'Check' }).click()
  await expect(page.locator('#code-hint')).toHaveText(
    'Enter a verification code',
  )
  expect(calls).toBe(0)

  const code = page.getByLabel('Verification code')
  await code.focus()
  await code.fill('ZZZZ-ZZZZ-ZZZZ-ZZZZ')
  await code.press('Enter')
  await expect(page.getByTestId('verify-result')).toHaveText(/Not found/)
  await expect(page.getByTestId('verify-result')).not.toContainText('Nino')

  await code.fill(VALID)
  await page.getByRole('button', { name: 'Check' }).click()
  const result = page.getByTestId('verify-result')
  await expect(result).toContainText('Valid')
  await expect(result).toContainText('Nino Beridze')
  await expect(result).toContainText('Machine Learning')
  await expect(result).toContainText('This is the latest version')
  await expect(result.getByRole('link')).toHaveAttribute(
    'href',
    /amoy\.polygonscan\.com/,
  )
  const animation = await result.evaluate(
    (element) => getComputedStyle(element).animationName,
  )
  expect(animation).toBe('none')

  await page.getByRole('button', { name: 'ქართული' }).click()
  await expect(result).toContainText('ვალიდური')
  await expect(result).toContainText('Machine Learning')

  await page.getByRole('button', { name: 'English' }).click()
  await page.getByLabel('Verification code').fill(OUTDATED)
  await page.getByRole('button', { name: 'Check' }).click()
  await expect(page.getByTestId('verify-result')).toContainText(
    'Outdated version',
  )
  await expect(page.getByTestId('verify-result')).toContainText('Python')
  await expect(page.getByTestId('verify-result')).toContainText(
    'This is not the latest version',
  )

  await page.getByLabel('Verification code').fill(PENDING)
  await page.getByRole('button', { name: 'Check' }).click()
  await expect(page.getByTestId('verify-result')).toHaveText(/Error/)
  await expect(page.getByTestId('verify-result')).not.toContainText('Python')
})
