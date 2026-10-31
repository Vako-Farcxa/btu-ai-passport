import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as api from '@/lib/api/admin'

import AdminAuditPage from './page'

vi.mock('@/lib/api/admin', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api/admin')>('@/lib/api/admin')
  return { ...actual, fetchAdminAudit: vi.fn() }
})

const entry = (
  over: Partial<api.AdminAuditEntry> = {},
): api.AdminAuditEntry => ({
  id: 'a1',
  created_at: '2026-10-30T10:00:00Z',
  actor: 'admin@btu.edu.ge',
  action: 'version.revoke',
  target_type: 'version',
  target: 'v-123',
  detail: { passport_id: 'BTU-ABC', version: 2 },
  ...over,
})

beforeEach(() => vi.mocked(api.fetchAdminAudit).mockReset())
afterEach(cleanup)

describe('admin activity page', () => {
  it('shows each change with a readable action and its details', async () => {
    vi.mocked(api.fetchAdminAudit).mockResolvedValue([
      entry(),
      entry({ id: 'a2', action: 'something.new', detail: {} }),
    ])
    render(<AdminAuditPage />)

    expect(await screen.findByText('Revoked a version')).toBeInTheDocument()
    expect(screen.getByText('passport id: BTU-ABC, version: 2')).toBeVisible()
    expect(screen.getAllByText('admin@btu.edu.ge')).toHaveLength(2)
    // An action code the page does not know yet is shown as it is.
    expect(screen.getByText('something.new')).toBeVisible()
    expect(api.fetchAdminAudit).toHaveBeenCalledWith(100)
  })

  it('says so when nothing was changed yet', async () => {
    vi.mocked(api.fetchAdminAudit).mockResolvedValue([])
    render(<AdminAuditPage />)
    expect(
      await screen.findByText('Nothing has been changed in the panel yet.'),
    ).toBeVisible()
  })

  it('shows the error and recovers on refresh', async () => {
    vi.mocked(api.fetchAdminAudit)
      .mockRejectedValueOnce(new Error('The activity log could not be loaded.'))
      .mockResolvedValueOnce([entry()])
    render(<AdminAuditPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'could not be loaded',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))

    expect(await screen.findByText('Revoked a version')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
