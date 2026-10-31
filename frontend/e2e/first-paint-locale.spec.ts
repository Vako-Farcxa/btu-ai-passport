import { expect, test, type Page } from '@playwright/test'

/** Georgian letters in <main>, ignoring the language switcher, which always says "ქართული". */
async function georgianText(page: Page): Promise<string> {
  const text = await page.locator('main').innerText()
  return (
    text
      .replace('ქართული', '')
      .match(/[\u10A0-\u10FF]+/g)
      ?.join(' ') ?? ''
  )
}

// With JavaScript off, what the server sent is all there is: no hydration can fix a wrong
// language afterwards. These tests are about that first paint.
test.describe('server-rendered language, JavaScript off', () => {
  test.use({ javaScriptEnabled: false })

  test.describe('an English browser', () => {
    test.use({ locale: 'en-US' })

    for (const path of ['/', '/verify', '/about', '/privacy', '/terms']) {
      test(`${path} arrives in English`, async ({ page }) => {
        await page.goto(path)
        await expect(page.locator('html')).toHaveAttribute('lang', 'en')
        await expect(
          page.getByRole('link', { name: /Skip to the main/ }),
        ).toBeAttached()
        expect(await georgianText(page)).toBe('')
      })
    }
  })

  test.describe('a Georgian browser', () => {
    test.use({ locale: 'ka-GE' })

    test('arrives in Georgian', async ({ page }) => {
      await page.goto('/about')
      await expect(page.locator('html')).toHaveAttribute('lang', 'ka')
      expect((await georgianText(page)).length).toBeGreaterThan(20)
    })
  })

  test.describe('the saved language choice', () => {
    test.use({ locale: 'en-US' })

    test('beats the browser language', async ({ page, context, baseURL }) => {
      await context.addCookies([
        { name: 'passport_locale', value: 'ka', url: baseURL! },
      ])
      await page.goto('/about')
      await expect(page.locator('html')).toHaveAttribute('lang', 'ka')
      expect((await georgianText(page)).length).toBeGreaterThan(20)
    })
  })

  test('a request with no Accept-Language is answered in English', async ({
    request,
  }) => {
    const response = await request.get('/', {
      headers: { 'Accept-Language': '' },
    })
    expect(response.status()).toBe(200)
    expect(await response.text()).toMatch(/<html lang="en"/)
  })

  test('the address does not show the language, and a language address is redirected', async ({
    page,
  }) => {
    const redirected = await page.request.get('/en/verify', { maxRedirects: 0 })
    expect(redirected.status()).toBe(308)
    expect(redirected.headers()['location']).toMatch(/\/verify$/)
    await page.goto('/ka/about')
    expect(new URL(page.url()).pathname).toBe('/about')
  })

  test('an unknown address shows the site 404 page with a 404 status', async ({
    page,
  }) => {
    const response = await page.goto('/no-such-page')
    expect(response?.status()).toBe(404)
    await expect(page.getByTestId('status-not_found')).toBeVisible()
  })
})

test.describe('with JavaScript on', () => {
  test.use({ locale: 'en-US' })

  test('an English visitor never renders Georgian text, even before hydration', async ({
    page,
  }) => {
    // Hold every script back so the page stays exactly as the server sent it.
    await page.route('**/_next/static/**/*.js', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1500))
      await route.continue()
    })
    await page.goto('/', { waitUntil: 'commit' })
    await page.waitForSelector('main')
    await expect(page.locator('html')).toHaveAttribute('lang', 'en')
    expect(await georgianText(page)).toBe('')
    await expect(page.getByRole('heading', { level: 1 })).toContainText(
      /passport/i,
    )
  })

  test('the verify page, which is filled in by the browser, is in the visitor language', async ({
    page,
  }) => {
    await page.goto('/verify')
    await expect(page.getByLabel('Verification code')).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  })

  test('choosing Georgian keeps working and is remembered on the next load', async ({
    page,
  }) => {
    await page.goto('/verify')
    await page.getByRole('button', { name: 'ქართული' }).click()
    await expect(page.locator('html')).toHaveAttribute('lang', 'ka')
    await page.reload()
    await expect(page.locator('html')).toHaveAttribute('lang', 'ka')
    expect((await georgianText(page)).length).toBeGreaterThan(20)
    await page.getByRole('button', { name: 'English' }).click()
    await page.reload()
    await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  })
})
