import { expect, test, type Page } from '@playwright/test'

import { hydrated } from './helpers'

const API = 'http://localhost:8000'

test.use({ locale: 'en-US' })

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: 'passport_mock_bearer', value: 'test-token', url: baseURL! },
  ])
})

const SKILL = {
  id: 'SKL-1',
  name: 'Machine Learning',
  name_ka: 'მანქანური სწავლება',
  category: 'AI Applied Skill',
  badge: 'BDG-AI-002',
  description: 'Choose a model the decision can survive.',
}

async function mockStudentsPage(page: Page) {
  await page.route(`${API}/admin/me`, (route) =>
    route.fulfill({ json: { email: 'admin@btu.edu.ge' } }),
  )
  await page.route(`${API}/admin/students**`, (route) =>
    route.fulfill({ json: { students: [], total: 0 } }),
  )
  await page.route(`${API}/admin/skills`, (route) =>
    route.fulfill({ json: { skills: [SKILL] } }),
  )
}

async function openDialog(page: Page) {
  await page.goto('/admin/students')
  const open = page.getByRole('button', { name: 'Add student' })
  await hydrated(open)
  await open.click()
  const dialog = page.getByRole('dialog', { name: 'Add student' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByLabel('Skill *')).toContainText('Machine Learning')
  return dialog
}

test('an admin adds a student and the request carries cleaned values', async ({
  page,
}) => {
  await mockStudentsPage(page)
  let sent: Record<string, unknown> | null = null
  await page.route(`${API}/admin/awards`, async (route) => {
    expect(route.request().headers().authorization).toBe('Bearer test-token')
    sent = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({
      json: {
        rows: [
          {
            email: 'nino.beridze@btu.edu.ge',
            status: 'synced',
            error: null,
            passport_id: 'BTU-A1B2C3D4E5',
            version: 1,
          },
        ],
        sync_result: {
          status: 'completed',
          rows_read: 1,
          versions_created: 1,
          error: null,
        },
      },
    })
  })

  const dialog = await openDialog(page)
  await dialog.getByLabel('First name *').fill('  Nino ')
  await dialog.getByLabel('Last name *').fill('Beridze')
  await dialog.getByLabel('BTU email *').fill('  Nino.Beridze@BTU.edu.ge ')
  await dialog.getByLabel('Skill *').selectOption('SKL-1')
  await dialog.getByRole('button', { name: 'Add student' }).click()

  await expect(dialog.getByRole('status')).toContainText(
    'Added. Passport BTU-A1B2C3D4E5, version 1.',
  )
  await expect(
    dialog.getByRole('link', { name: 'Open passport' }),
  ).toHaveAttribute('href', '/admin/students/BTU-A1B2C3D4E5')
  expect(sent).toMatchObject({
    skill_id: 'SKL-1',
    students: [
      {
        email: 'nino.beridze@btu.edu.ge',
        first_name: 'Nino',
        last_name: 'Beridze',
      },
    ],
  })
})

test('bad input is explained next to the field and nothing is sent', async ({
  page,
}) => {
  await mockStudentsPage(page)
  let calls = 0
  await page.route(`${API}/admin/awards`, async (route) => {
    calls += 1
    await route.abort()
  })

  const dialog = await openDialog(page)
  await dialog.getByLabel('First name *').fill('N1no')
  await dialog.getByLabel('BTU email *').fill('nino@gmail.com')
  await dialog.getByRole('button', { name: 'Add student' }).click()

  await expect(dialog.locator('#new-first-name-error')).toBeVisible()
  await expect(dialog.locator('#new-last-name-error')).toBeVisible()
  await expect(dialog.locator('#new-email-error')).toBeVisible()
  await expect(dialog.locator('#new-skill-error')).toContainText(
    'Choose a skill',
  )
  await expect(dialog.getByLabel('First name *')).toHaveAttribute(
    'aria-invalid',
    'true',
  )
  expect(calls).toBe(0)
})

test('a Sheet outage is shown in plain words and the form stays open', async ({
  page,
}) => {
  await mockStudentsPage(page)
  await page.route(`${API}/admin/awards`, (route) =>
    route.fulfill({ status: 503, json: { code: 'sheet_unavailable' } }),
  )

  const dialog = await openDialog(page)
  await dialog.getByLabel('First name *').fill('Nino')
  await dialog.getByLabel('Last name *').fill('Beridze')
  await dialog.getByLabel('BTU email *').fill('nino.beridze@btu.edu.ge')
  await dialog.getByLabel('Skill *').selectOption('SKL-1')
  await dialog.getByRole('button', { name: 'Add student' }).click()

  await expect(dialog.getByRole('alert')).toContainText(
    'The Google Sheet could not be reached. Nothing was saved.',
  )
  await expect(dialog.getByLabel('BTU email *')).toHaveValue(
    'nino.beridze@btu.edu.ge',
  )
})

test('Escape closes the dialog', async ({ page }) => {
  await mockStudentsPage(page)
  const dialog = await openDialog(page)
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
})
