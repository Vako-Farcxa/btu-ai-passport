import { expect, test, type Page } from '@playwright/test'

import { hydrated } from './helpers'

const FIRST = 'A1B2-C3D4-E5F6-G7H8'
const SECOND = 'K9M2-N3P4-Q5R6-S7T8'

const hash = (digit: string) => '0x' + digit.repeat(64)
const CONTRACT = '0x' + 'ab'.repeat(20)

function validFor(holder: string) {
  return {
    outcome: 'valid',
    holder_name: holder,
    version: 2,
    is_latest: true,
    skills: [
      { skill: 'Python', badge: 'BDG-AI-001', awarded_on: '2025-01-15' },
    ],
    tx_url: `https://amoy.polygonscan.com/tx/${hash('3')}`,
    onchain: {
      status: 'verified',
      block_number: 123,
      contract_address: CONTRACT,
      contract_url: `https://amoy.polygonscan.com/address/${CONTRACT}`,
      verification_id_hash: hash('1'),
      content_hash: hash('2'),
    },
  }
}

/** Answers the first code with Ana and any other code with Nino, and records every call. */
async function mockVerify(page: Page): Promise<string[]> {
  const codes: string[] = []
  await page.route('http://localhost:8000/verify', async (route) => {
    const { code } = route.request().postDataJSON() as { code: string }
    codes.push(code.trim().toUpperCase())
    const holder =
      code.trim().toUpperCase() === FIRST ? 'Ana Kiknadze' : 'Nino Beridze'
    await route.fulfill({ json: validFor(holder) })
  })
  return codes
}

test('editing the code leaves the shown result alone until the next submit', async ({
  page,
}) => {
  const codes = await mockVerify(page)
  await page.goto('/verify')
  const input = page.getByLabel('Verification code')
  await hydrated(input)
  await input.fill(FIRST)
  await input.press('Enter')

  const result = page.getByTestId('verify-result')
  await expect(result).toContainText('Ana Kiknadze')
  // Open the self-check details: a remounted result card would close them again.
  await page.getByText('Verify it yourself').click()
  const details = page.getByTestId('self-verify')
  await expect(details).toHaveJSProperty('open', true)
  const urlAfterCheck = page.url()

  // Type another code, key by key, without submitting.
  await input.fill('')
  await input.pressSequentially(SECOND.slice(0, 9), { delay: 20 })
  await expect(input).toHaveValue(SECOND.slice(0, 9))
  await page.waitForTimeout(400)
  await expect(result).toContainText('Ana Kiknadze')
  await expect(result).not.toContainText('Nino Beridze')
  await expect(details).toHaveJSProperty('open', true)
  expect(page.url()).toBe(urlAfterCheck)
  expect(codes).toEqual([FIRST])

  // Finish the code and press Enter: only now does the result change.
  await input.fill(SECOND)
  await expect(result).toContainText('Ana Kiknadze')
  expect(codes).toEqual([FIRST])
  await input.press('Enter')
  await expect(result).toContainText('Nino Beridze')
  await expect(result).not.toContainText('Ana Kiknadze')
  expect(codes).toEqual([FIRST, SECOND])
})

test('the Check button also submits, and a shared link is checked only once', async ({
  page,
}) => {
  const codes = await mockVerify(page)
  await page.goto(`/verify?code=${FIRST}`)
  const input = page.getByLabel('Verification code')
  await expect(page.getByTestId('verify-result')).toContainText('Ana Kiknadze')
  await expect(input).toHaveValue(FIRST)

  await input.fill(SECOND)
  await page.waitForTimeout(300)
  await expect(page.getByTestId('verify-result')).toContainText('Ana Kiknadze')
  // Typing does not rewrite the address bar either.
  expect(new URL(page.url()).searchParams.get('code')).toBe(FIRST)
  expect(codes).toEqual([FIRST])

  await page.getByRole('button', { name: 'Check' }).click()
  await expect(page.getByTestId('verify-result')).toContainText('Nino Beridze')
  expect(codes).toEqual([FIRST, SECOND])
})
