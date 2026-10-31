import { expect, test, type Page } from '@playwright/test'

import { hydrated } from './helpers'

const DATA = [
  'Nino Beridze',
  'Machine Learning',
  'BDG-AI-001',
  'Use models with a human in the loop.',
  // The placeholder is a sample code, not a sentence.
  'RXRP-F90C-ZRBZ-EP7T',
]
const TX = 'https://amoy.polygonscan.com/tx/0x' + '11'.repeat(32)

const found = {
  holder_name: 'Nino Beridze',
  skills: [
    {
      skill: 'Machine Learning',
      badge: 'BDG-AI-001',
      awarded_on: '2025-06-01',
      description: 'Use models with a human in the loop.',
    },
  ],
  tx_url: TX,
}

const BODIES: Record<string, object> = {
  VALID: { outcome: 'valid', version: 2, is_latest: true, ...found },
  OUTDATED: {
    outcome: 'outdated',
    version: 1,
    is_latest: false,
    latest_version: 3,
    latest_issued_at: '2026-10-28',
    ...found,
  },
  MISSING: { outcome: 'not_found' },
  BROKEN: { outcome: 'error' },
}

test.beforeEach(async ({ context, page, baseURL }) => {
  await context.addCookies([
    { name: 'passport_locale', value: 'ka', url: baseURL! },
  ])
  await page.route('http://localhost:8000/verify', async (route) => {
    const { code } = route.request().postDataJSON() as { code: string }
    await route.fulfill({ json: BODIES[code.toUpperCase()] })
  })
})

// All text and accessible names on the page, minus values that come from the API.
async function pageText(page: Page): Promise<string> {
  let text = await page.evaluate(() => {
    const root = document.querySelector('main') as HTMLElement
    const parts = [root.innerText]
    for (const element of root.querySelectorAll('*')) {
      for (const name of ['aria-label', 'title', 'alt']) {
        const value = element.getAttribute(name)
        if (value) parts.push(value)
      }
      const placeholder = element.getAttribute('placeholder')
      if (placeholder) parts.push(placeholder)
    }
    return parts.join('\n')
  })
  for (const value of DATA) text = text.split(value).join(' ')
  return text
}

// Brand and acronyms that stay Latin in Georgian text, plus the language switcher's
// fixed "English" label, which names the language in its own script on purpose.
// Polygon Amoy is the name of the test network, a proper noun.
const ALLOWED = new Set(['BTU', 'AI', 'English', 'Polygon', 'Amoy', 'GitHub'])

function englishWords(text: string): string[] {
  return (text.match(/[A-Za-z]{2,}/g) ?? []).filter(
    (word) => !ALLOWED.has(word),
  )
}

test('the verify page is fully Georgian before any check', async ({ page }) => {
  await page.goto('/verify')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'პასპორტის შემოწმება',
  )
  expect(englishWords(await pageText(page))).toEqual([])
  await expect(page.locator('html')).toHaveAttribute('lang', 'ka')
})

for (const code of Object.keys(BODIES)) {
  test(`the ${code} result page has no English text`, async ({ page }) => {
    await page.goto('/verify')
    await hydrated(page.getByLabel('შემოწმების კოდი'))
    await page.getByLabel('შემოწმების კოდი').fill(code)
    await page.getByRole('button', { name: 'შემოწმება' }).click()
    await expect(page.getByTestId('verify-result')).toBeVisible()
    expect(englishWords(await pageText(page))).toEqual([])
  })
}

test('the valid result shows Georgian labels and a locale formatted date', async ({
  page,
}) => {
  await page.goto('/verify')
  await hydrated(page.getByLabel('შემოწმების კოდი'))
  await page.getByLabel('შემოწმების კოდი').fill('VALID')
  await page.getByRole('button', { name: 'შემოწმება' }).click()
  const result = page.getByTestId('verify-result')
  await expect(result).toContainText('ნამდვილია')
  await expect(result).toContainText('პასპორტის მფლობელი')
  await expect(result).toContainText('საჯარო ტრანზაქცია')
  await expect(result.locator('time')).not.toHaveText('2025-06-01')
  await expect(result.locator('time')).toHaveText('1 ივნ. 2025')
})

test('the outdated result is Georgian including the newer version note', async ({
  page,
}) => {
  await page.goto('/verify')
  await hydrated(page.getByLabel('შემოწმების კოდი'))
  await page.getByLabel('შემოწმების კოდი').fill('OUTDATED')
  await page.getByRole('button', { name: 'შემოწმება' }).click()
  await expect(page.getByTestId('verify-result')).toContainText(
    'მოძველებული ვერსია',
  )
  await expect(page.getByTestId('newer-notice')).toContainText('v3')
  await expect(page.getByTestId('newer-notice')).toContainText('28 ოქტ. 2026')
})

test('the empty-code prompt is Georgian', async ({ page }) => {
  await page.goto('/verify')
  await hydrated(page.locator('#verification-code'))
  await page.getByRole('button', { name: 'შემოწმება' }).click()
  await expect(page.locator('#code-hint')).toHaveText(
    'შეიყვანეთ ვერიფიკაციის კოდი',
  )
})
