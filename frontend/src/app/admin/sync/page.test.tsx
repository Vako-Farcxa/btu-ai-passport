import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as api from '@/lib/api/admin'

import AdminSyncPage from './page'

vi.mock('@/lib/api/admin', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api/admin')>('@/lib/api/admin')
  return { ...actual, fetchAdminSyncRuns: vi.fn(), triggerAdminSync: vi.fn() }
})

const run = (over: Partial<api.AdminSyncRun> = {}): api.AdminSyncRun => ({
  id: 'r1',
  status: 'completed',
  started_at: '2026-10-31T10:00:00Z',
  finished_at: '2026-10-31T10:00:05Z',
  rows_read: 12,
  versions_created: 3,
  error: null,
  ...over,
})

beforeEach(() => {
  vi.mocked(api.fetchAdminSyncRuns).mockReset()
  vi.mocked(api.triggerAdminSync).mockReset()
  vi.mocked(api.fetchAdminSyncRuns).mockResolvedValue({ runs: [run()] })
})
afterEach(cleanup)

describe('sync monitor', () => {
  it('lists past runs with their counts', async () => {
    vi.mocked(api.fetchAdminSyncRuns).mockResolvedValue({
      runs: [
        run(),
        run({
          id: 'r2',
          status: 'failed',
          rows_read: null,
          versions_created: null,
          error: 'sheet_unavailable',
          finished_at: null,
        }),
      ],
    })
    render(<AdminSyncPage />)
    expect(await screen.findByText('completed')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeVisible()
    expect(screen.getByText('failed')).toBeVisible()
    expect(screen.getByText('sheet_unavailable')).toBeVisible()
    expect(screen.getByText('In Progress')).toBeVisible()
    expect(screen.getByText('None (Successful)')).toBeVisible()
    expect(api.fetchAdminSyncRuns).toHaveBeenCalledWith(50)
  })

  it('says so when no run was logged yet', async () => {
    vi.mocked(api.fetchAdminSyncRuns).mockResolvedValue({ runs: [] })
    render(<AdminSyncPage />)
    expect(
      await screen.findByText('No sync executions logged yet.'),
    ).toBeVisible()
  })

  it('shows an error when the history cannot load, and can be dismissed', async () => {
    vi.mocked(api.fetchAdminSyncRuns).mockRejectedValue(new Error('Nope'))
    render(<AdminSyncPage />)
    expect(await screen.findByText('Nope')).toBeVisible()
    fireEvent.click(screen.getByText('✕'))
    expect(screen.queryByText('Nope')).not.toBeInTheDocument()
  })

  it('runs a sync, reports the real outcome and reloads the history', async () => {
    vi.mocked(api.triggerAdminSync).mockResolvedValue({
      status: 'completed',
      rows_read: 5,
      versions_created: 2,
    })
    render(<AdminSyncPage />)
    await screen.findByText('completed')
    fireEvent.click(screen.getByRole('button', { name: 'Trigger Sync Now' }))
    expect(
      await screen.findByText(
        'Sync completed. Rows read: 5, new versions created: 2.',
      ),
    ).toBeVisible()
    await waitFor(() => expect(api.fetchAdminSyncRuns).toHaveBeenCalledTimes(2))
  })

  it('warns when another sync is running and never claims success', async () => {
    vi.mocked(api.triggerAdminSync).mockResolvedValue({
      status: 'skipped',
      rows_read: 0,
      versions_created: 0,
    })
    render(<AdminSyncPage />)
    await screen.findByText('completed')
    fireEvent.click(screen.getByRole('button', { name: 'Trigger Sync Now' }))
    expect(await screen.findByRole('status')).toHaveTextContent(
      'another sync is already running',
    )
    expect(screen.queryByText(/Sync completed/)).not.toBeInTheDocument()
  })

  it('shows the failure when the sync request itself fails', async () => {
    vi.mocked(api.triggerAdminSync).mockRejectedValue(
      new Error('Failed to trigger sync: Bad Gateway'),
    )
    render(<AdminSyncPage />)
    await screen.findByText('completed')
    fireEvent.click(screen.getByRole('button', { name: 'Trigger Sync Now' }))
    expect(
      await screen.findByText('Failed to trigger sync: Bad Gateway'),
    ).toBeVisible()
  })
})
