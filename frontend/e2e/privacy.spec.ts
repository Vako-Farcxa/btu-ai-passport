import { expect, test } from '@playwright/test'

test.use({ locale: 'en-US' })

test('the privacy page is linked from the footer and says what the site does with data', async ({
  page,
}) => {
  await page.goto('/verify')
  await page
    .locator('.site-footer-links')
    .getByRole('link', { name: 'Privacy' })
    .click()
  await expect(page).toHaveURL(/\/privacy$/)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Privacy')
  const article = page.getByTestId('info-privacy')
  await expect(article).toContainText('Signing in with Google')
  await expect(article).toContainText('Supabase')
  await expect(article).toContainText('contains no name, email, skill')
  await expect(article).toContainText(
    'no analytics, no advertising and no tracking',
  )
  await expect(article).not.toContainText(/not an official|hackathon/i)
  await expect(
    article.getByRole('link', { name: 'vpartskhaladze@gmail.com' }),
  ).toHaveAttribute('href', 'mailto:vpartskhaladze@gmail.com')
})

test('the privacy page switches to Georgian and back', async ({ page }) => {
  await page.goto('/privacy')
  await page.getByRole('button', { name: 'ქართული' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'კონფიდენციალურობა',
  )
  await expect(page.getByTestId('info-privacy')).toContainText(
    'vpartskhaladze@gmail.com',
  )
  await page.getByRole('button', { name: 'English' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Privacy')
})

test('the privacy page is in the sitemap and is not blocked for crawlers', async ({
  request,
}) => {
  const sitemap = await (await request.get('/sitemap.xml')).text()
  expect(sitemap).toContain('/privacy')
  const robots = await (await request.get('/robots.txt')).text()
  expect(robots).not.toMatch(/Disallow:\s*\/privacy/)
})
