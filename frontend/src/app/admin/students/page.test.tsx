import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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
    render(<AdminStudentsPage />)
    expect(await screen.findByText('Nino Beridze')).toBeInTheDocument()
    expect(screen.getByText('Gela Kapanadze')).toBeInTheDocument()
    expect(screen.queryByText('Old Student')).not.toBeInTheDocument()
    expect(
      screen.getAllByRole('link', { name: /View Details/ })[0],
    ).toHaveAttribute('href', '/admin/students/BTU-A1')
  })

  it('shows only admin managed students on that tab', async () => {
    render(<AdminStudentsPage />)
    await screen.findByText('Nino Beridze')
    fireEvent.click(screen.getByRole('button', { name: 'Admin Managed Only' }))
    await waitFor(() =>
      expect(screen.queryByText('Nino Beridze')).not.toBeInTheDocument(),
    )
    expect(screen.getByText('Gela Kapanadze')).toBeInTheDocument()
  })

  it('asks the API for archived students and shows them with a Restore button', async () => {
    render(<AdminStudentsPage />)
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
    render(<AdminStudentsPage />)
    expect(
      await screen.findByText('No students found matching your criteria.'),
    ).toBeVisible()
  })

  it('searches with the trimmed text', async () => {
    render(<AdminStudentsPage />)
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

  it('archives only after the admin confirms, then reloads', async () => {
    vi.mocked(api.deleteAdminStudent).mockResolvedValue(undefined)
    render(<AdminStudentsPage />)
    await screen.findByText('Nino Beridze')
    const row = screen.getByText('Nino Beridze').closest('tr') as HTMLElement

    vi.mocked(window.confirm).mockReturnValueOnce(false)
    fireEvent.click(within(row).getByRole('button', { name: 'Archive' }))
    expect(api.deleteAdminStudent).not.toHaveBeenCalled()

    const before = vi.mocked(api.fetchAdminStudents).mock.calls.length
    fireEvent.click(within(row).getByRole('button', { name: 'Archive' }))
    await waitFor(() =>
      expect(api.deleteAdminStudent).toHaveBeenCalledWith('BTU-A1'),
    )
    await waitFor(() =>
      expect(
        vi.mocked(api.fetchAdminStudents).mock.calls.length,
      ).toBeGreaterThan(before),
    )
  })

  it('tells the admin when archiving fails', async () => {
    vi.mocked(api.deleteAdminStudent).mockRejectedValue(
      new Error('This student is already archived.'),
    )
    render(<AdminStudentsPage />)
    await screen.findByText('Nino Beridze')
    const row = screen.getByText('Nino Beridze').closest('tr') as HTMLElement
    fireEvent.click(within(row).getByRole('button', { name: 'Archive' }))
    await waitFor(() =>
      expect(window.alert).toHaveBeenCalledWith(
        'This student is already archived.',
      ),
    )
  })

  it('restores an archived student after confirmation', async () => {
    vi.mocked(api.restoreAdminStudent).mockResolvedValue(undefined)
    render(<AdminStudentsPage />)
    await screen.findByText('Nino Beridze')
    fireEvent.click(
      screen.getByRole('button', { name: 'Archived / Soft-Deleted' }),
    )
    await screen.findByText('Old Student')
    fireEvent.click(screen.getByRole('button', { name: 'Restore' }))
    await waitFor(() =>
      expect(api.restoreAdminStudent).toHaveBeenCalledWith('BTU-A1'),
    )
  })

  it('opens and closes the add student dialog', async () => {
    render(<AdminStudentsPage />)
    await screen.findByText('Nino Beridze')
    fireEvent.click(screen.getByRole('button', { name: 'Add student' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close dialog' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
