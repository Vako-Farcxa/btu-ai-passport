import { expect, test } from '@playwright/test'

const CODE = 'A1B2-C3D4-E5F6-G7H8'

test('every page is sent with the security headers', async ({ request }) => {
  for (const path of ['/', '/verify', '/about', '/passport', '/admin']) {
    const response = await request.get(path)
    expect(response.status(), path).toBe(200)
    const headers = response.headers()
    const csp = headers['content-security-policy']
    expect(csp, path).toContain("default-src 'self'")
    expect(csp, path).toContain("frame-ancestors 'none'")
    expect(csp, path).toContain("object-src 'none'")
    expect(csp, path).toContain("connect-src 'self' http://localhost:8000")
    expect(headers['strict-transport-security']).toMatch(/max-age=\d+/)
    expect(headers['x-content-type-options']).toBe('nosniff')
    expect(headers['referrer-policy']).toBe('strict-origin-when-cross-origin')
    expect(headers['permissions-policy']).toContain('camera=()')
    expect(headers['x-frame-options']).toBe('DENY')
    expect(headers['x-powered-by']).toBeUndefined()
  }
})

test('the policy does not break the pages', async ({ page }) => {
  const violations: string[] = []
  page.on('console', (message) => {
    if (/content security policy/i.test(message.text())) {
      violations.push(message.text())
    }
  })
  await page.route('http://localhost:8000/verify', (route) =>
    route.fulfill({ json: { outcome: 'not_found' } }),
  )
  for (const path of ['/', '/verify', '/about', '/privacy', '/terms']) {
    await page.goto(path)
    await page.waitForLoadState('networkidle')
  }
  await page.goto('/verify')
  await page.fill('#verification-code', CODE)
  await page.click('button[type=submit]')
  await expect(page.getByText('Not found').first()).toBeVisible()
  expect(violations).toEqual([])
})

test('a 429 from the API shows a friendly message with the wait', async ({
  page,
}) => {
  await page.route('http://localhost:8000/verify', (route) =>
    route.fulfill({
      status: 429,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Expose-Headers': 'Retry-After',
        'Retry-After': '41',
      },
      json: { code: 'rate_limited' },
    }),
  )
  await page.goto('/verify')
  await page.fill('#verification-code', CODE)
  await page.click('button[type=submit]')
  await expect(page.locator('.page-alert')).toContainText(
    'Too many requests. Please wait 41 seconds and try again.',
  )
})

test('the 429 message follows the language', async ({ page, context }) => {
  await context.addCookies([
    { name: 'passport_locale', value: 'ka', domain: 'localhost', path: '/' },
  ])
  await page.route('http://localhost:8000/verify', (route) =>
    route.fulfill({
      status: 429,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Expose-Headers': 'Retry-After',
        'Retry-After': '41',
      },
      json: { code: 'rate_limited' },
    }),
  )
  await page.goto('/verify')
  await page.fill('#verification-code', CODE)
  await page.click('button[type=submit]')
  await expect(page.locator('.page-alert')).toContainText('41')
  await expect(page.locator('.page-alert')).toContainText(
    'ძალიან ბევრი მოთხოვნაა',
  )
})
