import { expect, test } from '@playwright/test'

import { hydrated } from './helpers'

const API = 'http://localhost:8000'

test.use({ locale: 'en-US' })

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: 'passport_mock_bearer', value: 'test-token', url: baseURL! },
  ])
})

const passport = {
  passport: {
    passport_id: 'BTU-A1B2C3D4E5',
    versions: [
      {
        version: 1,
        issued_at: '2026-10-01T00:00:00Z',
        is_current: true,
        holder_name: 'Nino Beridze',
        verification_code: 'A1B2-C3D4-E5F6-G7H8',
        skills: [],
        anchor: { status: 'pending', tx_url: null },
      },
    ],
  },
}

test('a student flags a version and the request carries only the comment', async ({
  page,
}) => {
  await page.route(`${API}/me/passport`, (route) =>
    route.fulfill({ json: passport }),
  )
  await page.route(`${API}/me/flags`, (route) =>
    route.fulfill({ json: { flags: [], unread: 0 } }),
  )
  let sent: Record<string, unknown> | null = null
  await page.route(`${API}/flags`, async (route) => {
    expect(route.request().headers().authorization).toBe('Bearer test-token')
    sent = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({
      status: 201,
      json: {
        id: 'f1',
        version: 1,
        comment: String(sent.comment),
        status: 'open',
        admin_note: '',
        created_at: '2026-10-31T10:00:00Z',
        resolved_at: null,
        unread: false,
      },
    })
  })

  await page.goto('/passport')
  const open = page.getByRole('button', { name: 'Flag an issue' })
  await hydrated(open)
  await open.click()

  const dialog = page.getByRole('dialog', {
    name: 'Flag an issue with version 1',
  })
  const comment = dialog.getByLabel('What looks wrong?')
  await comment.fill('Too short')
  await dialog.getByRole('button', { name: 'Send flag' }).click()
  await expect(dialog).toContainText('Please write at least 10 characters.')
  expect(sent).toBeNull()

  await comment.fill('  The Python skill is missing from this version.  ')
  await dialog.getByRole('button', { name: 'Send flag' }).click()
  await expect(dialog.getByRole('status')).toHaveText(
    'Thank you. Your flag was sent to the BTU team.',
  )
  expect(sent).toEqual({
    version: 1,
    comment: 'The Python skill is missing from this version.',
  })
})

test('a second flag on a version with an open flag is explained', async ({
  page,
}) => {
  await page.route(`${API}/me/passport`, (route) =>
    route.fulfill({ json: passport }),
  )
  await page.route(`${API}/me/flags`, (route) =>
    route.fulfill({ json: { flags: [], unread: 0 } }),
  )
  await page.route(`${API}/flags`, (route) =>
    route.fulfill({ status: 409, json: { code: 'flag_already_open' } }),
  )
  await page.goto('/passport')
  const open = page.getByRole('button', { name: 'Flag an issue' })
  await hydrated(open)
  await open.click()
  const dialog = page.getByRole('dialog')
  await dialog
    .getByLabel('What looks wrong?')
    .fill('The date on this version looks wrong.')
  await dialog.getByRole('button', { name: 'Send flag' }).click()
  await expect(dialog.getByRole('alert')).toHaveText(
    'This version already has an open flag.',
  )
})

test('an admin answers a flag and the reply is sent with the status', async ({
  page,
}) => {
  await page.route(`${API}/admin/me`, (route) =>
    route.fulfill({ json: { email: 'admin@btu.edu.ge' } }),
  )
  const flag = {
    id: 'f1',
    passport_id: 'BTU-A1B2C3D4E5',
    version: 1,
    verification_code: 'A1B2-C3D4-E5F6-G7H8',
    student_email: 'nino.beridze@btu.edu.ge',
    comment: 'The Python skill is missing from this version.',
    status: 'open',
    admin_note: '',
    resolved_by: null,
    created_at: '2026-10-31T10:00:00Z',
    resolved_at: null,
  }
  let answered = false
  await page.route(`${API}/admin/flags**`, async (route) => {
    if (route.request().method() === 'PATCH') return route.fallback()
    await route.fulfill({
      json: answered
        ? { flags: [], open_count: 0 }
        : { flags: [flag], open_count: 1 },
    })
  })
  let patch: Record<string, unknown> | null = null
  await page.route(`${API}/admin/flags/f1`, async (route) => {
    expect(route.request().method()).toBe('PATCH')
    patch = route.request().postDataJSON() as Record<string, unknown>
    answered = true
    await route.fulfill({
      json: {
        ...flag,
        status: 'resolved',
        admin_note: String(patch.admin_note),
        resolved_by: 'admin@btu.edu.ge',
        resolved_at: '2026-10-31T11:00:00Z',
      },
    })
  })

  await page.goto('/admin/flags')
  await expect(page.getByRole('tab', { name: 'Open (1)' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  await expect(page.getByText(flag.comment)).toBeVisible()
  const note = page.getByLabel('Reply to the student (optional)')
  await hydrated(note)
  await note.fill('  Fixed in the next sync.  ')
  await page.getByRole('button', { name: 'Resolve' }).click()

  await expect(page.getByText('No flags here.')).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Open (0)' })).toBeVisible()
  expect(patch).toEqual({
    status: 'resolved',
    admin_note: 'Fixed in the next sync.',
  })
})
