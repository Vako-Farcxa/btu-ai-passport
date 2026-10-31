import { expect, test, type Page } from '@playwright/test'

const CONTRACT = '0xf436Ba2A2cd1dc78f1543A1E7e8a9f20B2C40c32'
const FOUND = {
  outcome: 'valid',
  holder_name: 'Nino Beridze',
  version: 2,
  is_latest: true,
  skills: [
    {
      skill: 'Machine Learning',
      badge: 'BDG-AI-001',
      awarded_on: '2025-06-01',
    },
  ],
  tx_url: 'https://amoy.polygonscan.com/tx/0x' + '11'.repeat(32),
}
const ONCHAIN = {
  contract_address: CONTRACT,
  contract_url: `https://amoy.polygonscan.com/address/${CONTRACT}#readContract`,
  verification_id_hash: '0x' + 'ab'.repeat(32),
  content_hash: '0x' + 'cd'.repeat(32),
}

async function answer(page: Page, body: object) {
  await page.route('http://localhost:8000/verify', async (route) => {
    await route.fulfill({ json: body })
  })
  await page.goto('/verify')
  await page.getByLabel('Verification code').fill('A1B2-C3D4-E5F6-G7H8')
  await page.getByRole('button', { name: 'Check' }).click()
}

test('a verified result shows the on-chain badge, block link and self-check', async ({
  page,
}) => {
  await answer(page, {
    ...FOUND,
    onchain: { ...ONCHAIN, status: 'verified', block_number: 51378532 },
  })
  const badge = page.getByTestId('onchain-badge')
  await expect(badge).toContainText('Verified on-chain, block 51378532')
  await expect(page.getByTestId('onchain-block-link')).toHaveAttribute(
    'href',
    'https://amoy.polygonscan.com/block/51378532',
  )
  await page.getByTestId('self-verify').locator('summary').click()
  await expect(page.getByTestId('self-verify-link')).toHaveAttribute(
    'href',
    /address\/0xf436Ba2A2cd1dc78f1543A1E7e8a9f20B2C40c32#readContract$/,
  )
  await page.getByRole('button', { name: 'ქართული' }).click()
  await expect(badge).toContainText('დადასტურებულია ბლოკჩეინზე')
})

test('an unreachable chain keeps the result but never says verified', async ({
  page,
}) => {
  await answer(page, {
    ...FOUND,
    onchain: { ...ONCHAIN, status: 'unavailable', block_number: null },
  })
  const result = page.getByTestId('verify-result')
  await expect(result).toContainText('Nino Beridze')
  await expect(page.getByTestId('onchain-badge')).toContainText(
    'On-chain check unavailable, try later',
  )
  await expect(result).not.toContainText(/verified on-chain/i)
  await expect(page.getByTestId('onchain-block-link')).toHaveCount(0)
})

test('a tampered result shows no name or skills', async ({ page }) => {
  await answer(page, {
    outcome: 'tampered',
    reason: 'chain_mismatch',
    contract_url: ONCHAIN.contract_url,
  })
  const result = page.getByTestId('verify-result')
  await expect(result).toContainText('Does not match the blockchain')
  await expect(page.getByTestId('tampered-notice')).toBeVisible()
  await expect(result).not.toContainText('Nino')
  await expect(result).not.toContainText('Machine Learning')
  await expect(page.getByTestId('onchain-badge')).toHaveCount(0)
  await page.getByRole('button', { name: 'ქართული' }).click()
  await expect(result).toContainText('არ ემთხვევა ბლოკჩეინს')
})
