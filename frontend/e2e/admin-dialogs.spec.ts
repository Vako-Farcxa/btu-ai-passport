import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

import { hydrated } from './helpers'

const API = 'http://localhost:8000'

test.use({ locale: 'en-US' })

test.beforeEach(async ({ context, baseURL, page }) => {
  await context.addCookies([
    { name: 'passport_mock_bearer', value: 'test-token', url: baseURL! },
  ])
  // The point of these specs: the browser's own popups must never appear.
  page.on('dialog', (native) => {
    throw new Error(`Native ${native.type()}() was used: ${native.message()}`)
  })
})

const NINO = {
  id: 's1',
  email: 'nino@btu.edu.ge',
  full_name: 'Nino Beridze',
  passport_id: 'BTU-A1',
  admin_managed: false,
  deleted_at: null as string | null,
  version_count: 1,
  latest_anchor_status: 'confirmed',
  created_at: '2026-10-01T00:00:00Z',
}

async function mockAdmin(page: Page) {
  await page.route(`${API}/admin/me`, (route) =>
    route.fulfill({ json: { email: 'admin@btu.edu.ge' } }),
  )
}

/** The students list answers from `students`, which the archive and restore routes change. */
async function mockStudents(
  page: Page,
  students: (typeof NINO)[],
  actions: { archive?: number; restore?: number } = {},
) {
  const calls = { archive: 0, restore: 0 }
  await mockAdmin(page)
  await page.route(`${API}/admin/students**`, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'DELETE') {
      calls.archive += 1
      if (actions.archive && actions.archive !== 204) {
        return route.fulfill({
          status: actions.archive,
          json: { code: 'student_already_deleted' },
        })
      }
      Object.assign(students[0] ?? {}, { deleted_at: '2026-10-31T10:00:00Z' })
      return route.fulfill({ status: 204 })
    }
    if (request.method() === 'POST' && url.pathname.endsWith('/restore')) {
      calls.restore += 1
      Object.assign(students[0] ?? {}, { deleted_at: null })
      return route.fulfill({ status: 204 })
    }
    return route.fulfill({
      json: { students: structuredClone(students), total: students.length },
    })
  })
  return calls
}

async function openArchive(page: Page) {
  await page.goto('/admin/students')
  const archive = page.getByRole('button', { name: 'Archive', exact: true })
  await hydrated(archive)
  await archive.focus()
  await archive.press('Enter')
  const dialog = page.getByRole('alertdialog', {
    name: 'Archive Nino Beridze?',
  })
  await expect(dialog).toBeVisible()
  return { dialog, archive }
}

test.describe('archive a student', () => {
  test('the dialog is a danger confirmation with plain wording', async ({
    page,
  }) => {
    await mockStudents(page, [{ ...NINO }])
    const { dialog } = await openArchive(page)
    await expect(dialog).toContainText('Their codes will verify as Revoked')
    await expect(dialog).toContainText('you can restore them later')
    expect(await dialog.textContent()).not.toMatch(/[\u2013\u2014]/)
    const confirm = dialog.getByRole('button', { name: 'Archive student' })
    await expect(confirm).toHaveAttribute('data-variant', 'danger')
    // Focus starts on the safe choice, so a stray Enter cannot archive anyone.
    await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused()
  })

  test('Tab and Shift+Tab stay inside the dialog', async ({ page }) => {
    await mockStudents(page, [{ ...NINO }])
    const { dialog } = await openArchive(page)
    const cancel = dialog.getByRole('button', { name: 'Cancel' })
    const confirm = dialog.getByRole('button', { name: 'Archive student' })
    await expect(cancel).toBeFocused()
    // Six Tabs is more than enough to leave a two button dialog if focus could escape.
    // Focus may rest on an invisible guard for a moment before it moves back in.
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press('Tab')
      await expect
        .poll(() =>
          page.evaluate(() =>
            document.activeElement?.matches('[role="alertdialog"] button'),
          ),
        )
        .toBe(true)
    }
    await cancel.focus()
    await page.keyboard.press('Shift+Tab')
    await expect(confirm).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(cancel).toBeFocused()
  })

  test('Escape closes it, archives nobody and returns focus to the button', async ({
    page,
  }) => {
    const calls = await mockStudents(page, [{ ...NINO }])
    const { dialog, archive } = await openArchive(page)
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(archive).toBeFocused()
    expect(calls.archive).toBe(0)
  })

  test('Cancel closes it and archives nobody', async ({ page }) => {
    const calls = await mockStudents(page, [{ ...NINO }])
    const { dialog } = await openArchive(page)
    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).toHaveCount(0)
    await expect(page.getByText('Nino Beridze')).toBeVisible()
    expect(calls.archive).toBe(0)
  })

  test('confirming with the keyboard archives, toasts and refreshes the list', async ({
    page,
  }) => {
    const calls = await mockStudents(page, [{ ...NINO }])
    const { dialog } = await openArchive(page)
    await page.keyboard.press('Tab')
    await expect(
      dialog.getByRole('button', { name: 'Archive student' }),
    ).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(dialog).toHaveCount(0)
    const toast = page.getByTestId('toast')
    await expect(toast).toContainText('Student archived')
    await expect(toast).toHaveAttribute('data-type', 'success')
    await expect(page.getByText('No students found')).toBeVisible()
    expect(calls.archive).toBe(1)
  })

  test('a refused archive shows an error toast in plain words', async ({
    page,
  }) => {
    await mockStudents(page, [{ ...NINO }], { archive: 409 })
    const { dialog } = await openArchive(page)
    await dialog.getByRole('button', { name: 'Archive student' }).click()
    const toast = page.getByTestId('toast')
    await expect(toast).toHaveAttribute('data-type', 'error')
    await expect(toast).toContainText('Could not archive the student')
    await expect(toast).toContainText('This student is already archived.')
  })

  test('a toast can be dismissed', async ({ page }) => {
    await mockStudents(page, [{ ...NINO }])
    const { dialog } = await openArchive(page)
    await dialog.getByRole('button', { name: 'Archive student' }).click()
    const toast = page.getByTestId('toast')
    await expect(toast).toBeVisible()
    await toast.getByLabel('Dismiss notification').click({ force: true })
    await expect(toast).toHaveCount(0)
  })

  test('the open dialog has no serious accessibility violations', async ({
    page,
  }) => {
    await mockStudents(page, [{ ...NINO }])
    await openArchive(page)
    // Axe measures colour contrast, so let the fade-in finish first.
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            document
              .getAnimations()
              .filter(
                (a) => a.effect?.getComputedTiming().iterations !== Infinity,
              )
              .filter((a) => a.playState === 'running').length,
        ),
      )
      .toBe(0)
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()
    expect(
      results.violations
        .filter((v) => v.impact === 'serious' || v.impact === 'critical')
        .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })),
    ).toEqual([])
  })
})

test('restoring an archived student asks first and is not styled as danger', async ({
  page,
}) => {
  const calls = await mockStudents(page, [
    { ...NINO, deleted_at: '2026-10-30T10:00:00Z' },
  ])
  await page.goto('/admin/students')
  const tab = page.getByRole('button', { name: 'Archived / Soft-Deleted' })
  await hydrated(tab)
  await tab.click()
  await page.getByRole('button', { name: 'Restore', exact: true }).click()
  const dialog = page.getByRole('alertdialog', {
    name: 'Restore Nino Beridze?',
  })
  await expect(dialog).toBeVisible()
  const confirm = dialog.getByRole('button', { name: 'Restore student' })
  await expect(confirm).toHaveAttribute('data-variant', 'default')
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  expect(calls.restore).toBe(0)

  await page.getByRole('button', { name: 'Restore', exact: true }).click()
  await dialog.getByRole('button', { name: 'Restore student' }).click()
  await expect(page.getByTestId('toast')).toContainText('Student restored')
  expect(calls.restore).toBe(1)
})

const VERSION = {
  id: 'v1',
  version_number: 1,
  holder_name: 'Nino Beridze',
  verification_code: 'AAAA-BBBB-CCCC-DDDD',
  anchor_status: 'confirmed',
  anchor_attempts: 1,
  anchor_last_error: null,
  tx_hash: null,
  issued_at: '2026-10-28T10:00:00Z',
  revoked_at: null as string | null,
  skills: [],
}

test.describe('revoke a version', () => {
  async function mockDetail(page: Page) {
    const state = { revoke: 0, version: { ...VERSION } }
    await mockAdmin(page)
    await page.route(`${API}/admin/students/BTU-A1`, (route) =>
      route.fulfill({
        json: {
          email: NINO.email,
          full_name: NINO.full_name,
          passport_id: NINO.passport_id,
          admin_managed: false,
          deleted_at: null,
          versions: [state.version],
        },
      }),
    )
    await page.route(`${API}/admin/versions/v1/revoke`, (route) => {
      state.revoke += 1
      state.version.revoked_at = '2026-10-31T10:00:00Z'
      return route.fulfill({ status: 204 })
    })
    return state
  }

  test('Escape cancels, Enter on Revoke confirms, and the page updates', async ({
    page,
  }) => {
    const state = await mockDetail(page)
    await page.goto('/admin/students/BTU-A1')
    const trigger = page.getByRole('button', { name: 'Revoke version' })
    await hydrated(trigger)
    await trigger.focus()
    await trigger.press('Enter')
    const dialog = page.getByRole('alertdialog', { name: 'Revoke version 1?' })
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('You can restore it later.')
    await expect(
      dialog.getByRole('button', { name: 'Revoke version' }),
    ).toHaveAttribute('data-variant', 'danger')

    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(trigger).toBeFocused()
    expect(state.revoke).toBe(0)

    await trigger.press('Enter')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(
      dialog.getByRole('button', { name: 'Revoke version' }),
    ).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('toast')).toContainText('Version 1 revoked')
    await expect(page.getByText(/^REVOKED/)).toBeVisible()
    await expect(
      page.getByRole('button', { name: 'Restore version' }),
    ).toBeVisible()
    expect(state.revoke).toBe(1)
  })
})

test('Trigger Sync reports its result in a toast, not a browser popup', async ({
  page,
}) => {
  await mockAdmin(page)
  await page.route(`${API}/admin/stats`, (route) =>
    route.fulfill({
      json: {
        total_students: 0,
        admin_managed_students: 0,
        pending_anchors: 0,
        failed_anchors: 0,
        open_flags: 0,
        recent_runs: [],
      },
    }),
  )
  await page.route(`${API}/admin/health`, (route) =>
    route.fulfill({
      json: { status: 'ok', alerts: [], checked_at: '2026-10-31T10:00:00Z' },
    }),
  )
  await page.route(`${API}/admin/sync`, (route) =>
    route.fulfill({
      json: {
        status: 'skipped',
        rows_read: 0,
        versions_created: 0,
        error: null,
      },
    }),
  )
  await page.goto('/admin')
  const sync = page.getByRole('button', { name: 'Trigger Sync' })
  await hydrated(sync)
  await sync.click()
  const toast = page.getByTestId('toast')
  await expect(toast).toHaveAttribute('data-type', 'warning')
  await expect(toast).toContainText('Sync skipped')
  await expect(toast).toContainText('another sync is already running')
})
