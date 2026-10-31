import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminFeedback } from '@/components/admin/admin-feedback'
import * as api from '@/lib/api/admin'

import AdminStudentsPage from './page'

vi.mock('@/lib/api/admin', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api/admin')>('@/lib/api/admin')
  return {
    ...actual,
    fetchAdminStudents: vi.fn(),
    deleteAdminStudent: vi.fn(),
    restoreAdminStudent: vi.fn(),
  }
})
vi.mock('@/components/admin/add-student-dialog', () => ({
  AddStudentDialog: ({ onClose }: { onClose: () => void }) => (
    <div role="dialog" aria-label="Add student dialog">
      <button onClick={onClose}>Close dialog</button>
    </div>
  ),
}))

function renderPage() {
  return render(
    <AdminFeedback>
      <AdminStudentsPage />
    </AdminFeedback>,
  )
}

const firstArchiveButton = () =>
  screen.getAllByRole('button', { name: 'Archive' })[0] as HTMLElement

const confirmDialog = () => screen.findByRole('alertdialog')

const student = (over: Partial<api.AdminStudent> = {}): api.AdminStudent => ({
  id: 's1',
  email: 'nino@btu.edu.ge',
  full_name: 'Nino Beridze',
  passport_id: 'BTU-A1',
  admin_managed: false,
  deleted_at: null,
  version_count: 2,
  latest_anchor_status: 'confirmed',
  created_at: '2026-10-01T00:00:00Z',
  ...over,
})

beforeEach(() => {
  vi.mocked(api.fetchAdminStudents).mockReset()
  vi.mocked(api.deleteAdminStudent).mockReset()
  vi.mocked(api.restoreAdminStudent).mockReset()
  vi.mocked(api.fetchAdminStudents).mockResolvedValue({
    students: [
      student(),
      student({ id: 's2', full_name: 'Gela Kapanadze', admin_managed: true }),
      student({
        id: 's3',
        full_name: 'Old Student',
        deleted_at: '2026-10-02T00:00:00Z',
      }),
    ],
    total: 3,
  })
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  vi.spyOn(window, 'alert').mockImplementation(() => undefined)
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('student directory', () => {
  it('lists active students and hides archived ones by default', async () => {
    renderPage()
    expect(await screen.findByText('Nino Beridze')).toBeInTheDocument()
    expect(screen.getByText('Gela Kapanadze')).toBeInTheDocument()
    expect(screen.queryByText('Old Student')).not.toBeInTheDocument()
    expect(
      screen.getAllByRole('link', { name: /View Details/ })[0],
    ).toHaveAttribute('href', '/admin/students/BTU-A1')
  })

  it('shows only admin managed students on that tab', async () => {
    renderPage()
    await screen.findByText('Nino Beridze')
    fireEvent.click(screen.getByRole('button', { name: 'Admin Managed Only' }))
    await waitFor(() =>
      expect(screen.queryByText('Nino Beridze')).not.toBeInTheDocument(),
    )
    expect(screen.getByText('Gela Kapanadze')).toBeInTheDocument()
  })

  it('asks the API for archived students and shows them with a Restore button', async () => {
    renderPage()
    await screen.findByText('Nino Beridze')
    fireEvent.click(
      screen.getByRole('button', { name: 'Archived / Soft-Deleted' }),
    )
    expect(await screen.findByText('Old Student')).toBeInTheDocument()
    expect(api.fetchAdminStudents).toHaveBeenLastCalledWith(
      expect.objectContaining({ includeDeleted: true }),
    )
    expect(screen.queryByText('Nino Beridze')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Restore' })).toBeInTheDocument()
  })

  it('says when nothing matches', async () => {
    vi.mocked(api.fetchAdminStudents).mockResolvedValue({
      students: [],
      total: 0,
    })
    renderPage()
    expect(
      await screen.findByText('No students found matching your criteria.'),
    ).toBeVisible()
  })

  it('searches with the trimmed text', async () => {
    renderPage()
    await screen.findByText('Nino Beridze')
    fireEvent.change(screen.getByPlaceholderText('Search name or email...'), {
      target: { value: '  nino ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Filter' }))
    await waitFor(() =>
      expect(api.fetchAdminStudents).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: 'nino' }),
      ),
    )
  })

  it('never uses the browser popups', async () => {
    vi.mocked(api.deleteAdminStudent).mockResolvedValue(undefined)
    renderPage()
    await screen.findByText('Nino Beridze')
    fireEvent.click(firstArchiveButton())
    const dialog = await confirmDialog()
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Archive student' }),
    )
    await waitFor(() => expect(api.deleteAdminStudent).toHaveBeenCalled())
    expect(window.confirm).not.toHaveBeenCalled()
    expect(window.alert).not.toHaveBeenCalled()
  })

  it('asks in a danger dialog before archiving and names the student', async () => {
    renderPage()
    await screen.findByText('Nino Beridze')
    const row = screen.getByText('Nino Beridze').closest('tr') as HTMLElement
    fireEvent.click(within(row).getByRole('button', { name: 'Archive' }))
    const dialog = await confirmDialog()
    expect(dialog).toHaveAccessibleName('Archive Nino Beridze?')
    expect(dialog).toHaveAccessibleDescription(/codes will verify as Revoked/)
    expect(dialog.textContent).not.toMatch(/\u2014|\u2013/)
    expect(
      within(dialog).getByRole('button', { name: 'Archive student' }),
    ).toHaveAttribute('data-variant', 'danger')
    expect(api.deleteAdminStudent).not.toHaveBeenCalled()
  })

  it('archives after the admin confirms, shows a toast and reloads', async () => {
    vi.mocked(api.deleteAdminStudent).mockResolvedValue(undefined)
    renderPage()
    await screen.findByText('Nino Beridze')
    const row = screen.getByText('Nino Beridze').closest('tr') as HTMLElement
    const before = vi.mocked(api.fetchAdminStudents).mock.calls.length
    fireEvent.click(within(row).getByRole('button', { name: 'Archive' }))
    const dialog = await confirmDialog()
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Archive student' }),
    )
    await waitFor(() =>
      expect(api.deleteAdminStudent).toHaveBeenCalledWith('BTU-A1'),
    )
    await waitFor(() =>
      expect(
        vi.mocked(api.fetchAdminStudents).mock.calls.length,
      ).toBeGreaterThan(before),
    )
    expect(
      (await screen.findAllByText('Student archived')).length,
    ).toBeGreaterThan(0)
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument(),
    )
  })

  it('does nothing when the admin presses Cancel', async () => {
    renderPage()
    await screen.findByText('Nino Beridze')
    fireEvent.click(firstArchiveButton())
    const dialog = await confirmDialog()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument(),
    )
    expect(api.deleteAdminStudent).not.toHaveBeenCalled()
  })

  it('closes on Escape without archiving, and focus starts on Cancel', async () => {
    renderPage()
    await screen.findByText('Nino Beridze')
    fireEvent.click(firstArchiveButton())
    const dialog = await confirmDialog()
    await waitFor(() =>
      expect(
        within(dialog).getByRole('button', { name: 'Cancel' }),
      ).toHaveFocus(),
    )
    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: 'Escape',
    })
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument(),
    )
    expect(api.deleteAdminStudent).not.toHaveBeenCalled()
  })

  it('tells the admin in an error toast when archiving fails', async () => {
    vi.mocked(api.deleteAdminStudent).mockRejectedValue(
      new Error('This student is already archived.'),
    )
    renderPage()
    await screen.findByText('Nino Beridze')
    const row = screen.getByText('Nino Beridze').closest('tr') as HTMLElement
    fireEvent.click(within(row).getByRole('button', { name: 'Archive' }))
    const dialog = await confirmDialog()
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Archive student' }),
    )
    expect(
      (await screen.findAllByText('This student is already archived.')).length,
    ).toBeGreaterThan(0)
    expect(
      screen.getAllByText('Could not archive the student').length,
    ).toBeGreaterThan(0)
    expect(window.alert).not.toHaveBeenCalled()
  })

  it('restores an archived student after a normal (not danger) confirmation', async () => {
    vi.mocked(api.restoreAdminStudent).mockResolvedValue(undefined)
    renderPage()
    await screen.findByText('Nino Beridze')
    fireEvent.click(
      screen.getByRole('button', { name: 'Archived / Soft-Deleted' }),
    )
    await screen.findByText('Old Student')
    fireEvent.click(screen.getByRole('button', { name: 'Restore' }))
    const dialog = await confirmDialog()
    expect(dialog).toHaveAccessibleName('Restore Old Student?')
    const confirmButton = within(dialog).getByRole('button', {
      name: 'Restore student',
    })
    expect(confirmButton).toHaveAttribute('data-variant', 'default')
    fireEvent.click(confirmButton)
    await waitFor(() =>
      expect(api.restoreAdminStudent).toHaveBeenCalledWith('BTU-A1'),
    )
    expect(
      (await screen.findAllByText('Student restored')).length,
    ).toBeGreaterThan(0)
  })

  it('opens and closes the add student dialog', async () => {
    renderPage()
    await screen.findByText('Nino Beridze')
    fireEvent.click(screen.getByRole('button', { name: 'Add student' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close dialog' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
