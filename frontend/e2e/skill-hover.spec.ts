import { expect, test, type Page } from '@playwright/test'

const DESCRIPTION = 'Use models with a human in the loop.'
const TX = 'https://amoy.polygonscan.com/tx/0x' + '11'.repeat(32)

test.use({ locale: 'en-US' })

async function openResult(
  page: Page,
  labels = { code: 'Verification code', check: 'Check' },
) {
  await page.route('http://localhost:8000/verify', async (route) => {
    await route.fulfill({
      json: {
        outcome: 'valid',
        holder_name: 'Nino Beridze',
        version: 2,
        is_latest: true,
        skills: [
          {
            skill: 'Machine Learning',
            badge: 'BDG-AI-002',
            awarded_on: '2025-06-01',
            description: DESCRIPTION,
          },
        ],
        tx_url: TX,
      },
    })
  })
  await page.goto('/verify')
  await page.getByLabel(labels.code).fill('A1B2-C3D4-E5F6-G7H8')
  await page.getByRole('button', { name: labels.check }).click()
  await expect(page.getByTestId('verify-result')).toBeVisible()
}

const LEVEL = 'AI Applied Skill · Applied learning'

test('the description opens from the skill name and Esc closes it', async ({
  page,
}) => {
  await openResult(page)
  const name = page.getByRole('button', { name: 'Machine Learning' })
  await expect(page.getByText(DESCRIPTION)).toBeHidden()
  await expect(name).toHaveAttribute('aria-expanded', 'false')

  await name.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByText(DESCRIPTION)).toBeVisible()
  await expect(name).toHaveAttribute('aria-expanded', 'true')

  await page.keyboard.press('Escape')
  await expect(page.getByText(DESCRIPTION)).toBeHidden()
  await expect(name).toBeFocused()
})

test('hovering the stamp explains the badge level', async ({ page }) => {
  await openResult(page)
  const stamp = page.getByRole('button', { name: LEVEL })
  const tip = page.getByRole('tooltip')
  await expect(tip).not.toHaveClass(/open/)
  await stamp.hover()
  await expect(tip).toHaveClass(/open/)
  await expect(tip).toContainText(
    'Awarded for applying an AI skill in practice.',
  )
  await page.getByRole('heading', { level: 1 }).hover()
  await expect(tip).not.toHaveClass(/open/)
})

test('the stamp tooltip works from the keyboard and Esc closes it', async ({
  page,
}) => {
  await openResult(page)
  const stamp = page.getByRole('button', { name: LEVEL })
  const tip = page.getByRole('tooltip')
  await page.getByRole('button', { name: 'Machine Learning' }).focus()
  await page.keyboard.press('Tab')
  await expect(stamp).toBeFocused()
  await expect(tip).toHaveClass(/open/)
  await expect(stamp).toHaveAttribute(
    'aria-describedby',
    (await tip.getAttribute('id')) ?? '',
  )
  await page.keyboard.press('Escape')
  await expect(tip).not.toHaveClass(/open/)
  await expect(stamp).toBeFocused()
})

test('the tooltip text stays available to screen readers while closed', async ({
  page,
}) => {
  await openResult(page)
  const tip = page.getByRole('tooltip')
  await expect(tip).not.toHaveClass(/open/) // clipped off screen
  await expect(tip).toHaveText(/Awarded for applying an AI skill in practice\./)
  await expect(
    page.getByRole('button', { name: LEVEL }),
  ).toHaveAccessibleDescription(
    /Awarded for applying an AI skill in practice\./,
  )
})

test('the tooltip and disclosure are Georgian in Georgian', async ({
  page,
  context,
}) => {
  await context.addCookies([
    { name: 'passport_locale', value: 'ka', url: 'http://localhost:3000' },
  ])
  await openResult(page, { code: 'შემოწმების კოდი', check: 'შემოწმება' })
  const level = page.getByRole('button', {
    name: 'AI გამოყენებითი უნარი · გამოყენებითი სწავლა',
  })
  await level.hover()
  await expect(page.getByRole('tooltip')).toHaveClass(/open/)
  await expect(page.getByRole('tooltip')).toContainText('ენიჭება')
})

test.describe('on a touch screen', () => {
  test.use({ hasTouch: true })

  test('a tap shows the tooltip and a tap elsewhere hides it', async ({
    page,
  }) => {
    await openResult(page)
    const tip = page.getByRole('tooltip')
    await page.getByRole('button', { name: LEVEL }).tap()
    await expect(tip).toHaveClass(/open/)
    await page.getByRole('heading', { level: 1 }).tap()
    await expect(tip).not.toHaveClass(/open/)
  })

  test('a tap on the skill name opens the description', async ({ page }) => {
    await openResult(page)
    await page.getByRole('button', { name: 'Machine Learning' }).tap()
    await expect(page.getByText(DESCRIPTION)).toBeVisible()
  })
})

test('the verify result still has no animation', async ({ page }) => {
  await openResult(page)
  const animation = await page
    .getByTestId('verify-result')
    .evaluate((element) => getComputedStyle(element).animationName)
  expect(animation).toBe('none')
})
