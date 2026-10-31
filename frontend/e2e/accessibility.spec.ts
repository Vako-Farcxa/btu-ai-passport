import { expect, test } from '@playwright/test'

test.use({ locale: 'en-US' })

for (const path of ['/', '/verify', '/about', '/privacy', '/terms']) {
  test(`${path}: the first Tab stop skips to the main content`, async ({
    page,
  }) => {
    await page.goto(path)
    await page.keyboard.press('Tab')
    const skip = page.getByRole('link', { name: 'Skip to the main content' })
    await expect(skip).toBeFocused()
    await expect(skip).toBeInViewport()
    await page.keyboard.press('Enter')
    await expect(page.locator('main#main')).toBeFocused()
  })
}

test('the skip link stays out of sight until it has focus', async ({
  page,
}) => {
  await page.goto('/verify')
  const skip = page.getByRole('link', { name: 'Skip to the main content' })
  await expect(skip).not.toBeInViewport()
})

test('links and buttons in the header and footer are at least 44 px tall', async ({
  page,
}) => {
  await page.goto('/verify')
  const targets = page.locator(
    '.topbar a, .topbar button, .site-footer-links a',
  )
  const count = await targets.count()
  expect(count).toBeGreaterThan(4)
  for (let i = 0; i < count; i++) {
    const box = await targets.nth(i).boundingBox()
    expect(box?.height, `target ${i}`).toBeGreaterThanOrEqual(43.5)
  }
})
