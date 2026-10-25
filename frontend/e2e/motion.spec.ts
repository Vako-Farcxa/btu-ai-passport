import { expect, test } from '@playwright/test'

test('sign-in and verify are reachable by keyboard only', async ({ page }) => {
  await page.goto('/')
  await page.keyboard.press('Tab')
  // Cycle focusable elements until Verify link is focused
  for (let i = 0; i < 10; i++) {
    const active = await page.evaluate(() =>
      document.activeElement?.closest('a')?.getAttribute('href'),
    )
    if (active === '/verify') break
    await page.keyboard.press('Tab')
  }
  await expect(page.getByRole('link', { name: /verify a code/i })).toBeFocused()
  await page.keyboard.press('Enter')
  await page.getByLabel('Verification code').fill('K9M2-N3P4-Q5R6-S7T8')
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('verify-result')).toBeVisible()
})

test('the home page does not animate its main under reduced motion', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await expect(page.locator('main')).toHaveCSS('animation-name', 'none')

  await page.getByRole('link', { name: /verify a code/i }).click()
  await page.getByLabel('Verification code').fill('A1B2-C3D4-E5F6-G7H8')
  await page.getByRole('button', { name: /check/i }).click()
  const result = page.getByTestId('verify-result')
  await expect(result).toBeVisible()
  const animation = await result.evaluate(
    (element) => getComputedStyle(element).animationName,
  )
  expect(animation).toBe('none')
})

test('the verify page never imports an entrance animation', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/verify')
  await expect(page.locator('[data-testid="verify-result"]')).not.toBeVisible()
  await page.getByLabel('Verification code').fill('A1B2-C3D4-E5F6-G7H8')
  await page.getByRole('button', { name: /check/i }).click()
  const result = page.getByTestId('verify-result')
  await expect(result).toBeVisible()
  const animation = await result.evaluate(
    (element) => getComputedStyle(element).animationName,
  )
  expect(animation).toBe('none')
})
