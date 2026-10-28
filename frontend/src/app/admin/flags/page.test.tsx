import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as api from '@/lib/api/admin'

import AdminFlagsPage from './page'

vi.mock('@/lib/api/admin', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api/admin')>('@/lib/api/admin')
  return { ...actual, fetchAdminFlags: vi.fn(), updateAdminFlag: vi.fn() }
})

const flag: api.AdminFlag = {
  id: 'f1',
  passport_id: 'BTU-ABC',
  version: 2,
  verification_code: 'AAAA-BBBB-CCCC-DDDD',
  student_email: 'nino@btu.edu.ge',
  comment: 'The Python skill is missing.',
  status: 'open',
  admin_note: '',
  resolved_by: null,
  created_at: '2026-10-28T10:00:00Z',
  resolved_at: null,
}

beforeEach(() => {
  vi.mocked(api.fetchAdminFlags).mockReset()
  vi.mocked(api.updateAdminFlag).mockReset()
  vi.mocked(api.fetchAdminFlags).mockResolvedValue({
    flags: [flag],
    open_count: 1,
  })
})
afterEach(cleanup)

describe('admin flags page', () => {
  it('lists open flags first with a verify link carrying the code', async () => {
    render(<AdminFlagsPage />)
    expect(await screen.findByText('nino@btu.edu.ge')).toBeInTheDocument()
    expect(api.fetchAdminFlags).toHaveBeenCalledWith('open')
    expect(screen.getByText('The Python skill is missing.')).toBeVisible()
    expect(
      screen.getByRole('link', { name: /Verify this version/ }),
    ).toHaveAttribute('href', '/verify?code=AAAA-BBBB-CCCC-DDDD')
    expect(screen.getByRole('tab', { name: /Open \(1\)/ })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  it('filters by status', async () => {
    render(<AdminFlagsPage />)
    await screen.findByText('nino@btu.edu.ge')
    fireEvent.click(screen.getByRole('tab', { name: 'Resolved' }))
    await waitFor(() =>
      expect(api.fetchAdminFlags).toHaveBeenLastCalledWith('resolved'),
    )
    fireEvent.click(screen.getByRole('tab', { name: 'All' }))
    await waitFor(() =>
      expect(api.fetchAdminFlags).toHaveBeenLastCalledWith(undefined),
    )
  })

  it('resolves with a note and reloads', async () => {
    vi.mocked(api.updateAdminFlag).mockResolvedValue({
      ...flag,
      status: 'resolved',
    })
    render(<AdminFlagsPage />)
    await screen.findByText('nino@btu.edu.ge')
    fireEvent.change(screen.getByLabelText(/Reply to the student/), {
      target: { value: '  Added the skill.  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Resolve' }))
    await waitFor(() =>
      expect(api.updateAdminFlag).toHaveBeenCalledWith('f1', {
        status: 'resolved',
        admin_note: 'Added the skill.',
      }),
    )
    await waitFor(() => expect(api.fetchAdminFlags).toHaveBeenCalledTimes(2))
  })

  it('dismisses without a note', async () => {
    vi.mocked(api.updateAdminFlag).mockResolvedValue({
      ...flag,
      status: 'dismissed',
    })
    render(<AdminFlagsPage />)
    await screen.findByText('nino@btu.edu.ge')
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    await waitFor(() =>
      expect(api.updateAdminFlag).toHaveBeenCalledWith('f1', {
        status: 'dismissed',
        admin_note: '',
      }),
    )
  })

  it('refuses a note over 500 characters before sending', async () => {
    render(<AdminFlagsPage />)
    await screen.findByText('nino@btu.edu.ge')
    fireEvent.change(screen.getByLabelText(/Reply to the student/), {
      target: { value: 'n'.repeat(501) },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Resolve' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('500')
    expect(api.updateAdminFlag).not.toHaveBeenCalled()
  })
})
