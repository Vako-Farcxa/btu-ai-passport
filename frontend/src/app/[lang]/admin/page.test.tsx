import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminFeedback } from '@/components/admin/admin-feedback'
import * as api from '@/lib/api/admin'

import AdminDashboardPage from './page'

vi.mock('@/lib/api/admin', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api/admin')>('@/lib/api/admin')
  return {
    ...actual,
    fetchAdminStats: vi.fn(),
    fetchAdminStudents: vi.fn(),
    fetchAdminPendingVersions: vi.fn(),
    fetchAdminSyncRuns: vi.fn(),
    fetchAdminFlags: vi.fn(),
    fetchAdminHealth: vi.fn(),
    triggerAdminSync: vi.fn(),
  }
})

const stats: api.AdminStats = {
  total_students: 214,
  admin_managed_students: 9,
  pending_anchors: 3,
  failed_anchors: 1,
  open_flags: 2,
  recent_runs: [
    {
      id: 'run-1',
      status: 'completed',
      started_at: '2026-10-31T12:00:00Z',
      finished_at: '2026-10-31T12:00:20Z',
      rows_read: 640,
      versions_created: 0,
      error: null,
    },
  ],
}

beforeEach(() => {
  vi.mocked(api.fetchAdminStats).mockReset()
  vi.mocked(api.fetchAdminHealth).mockReset()
  vi.mocked(api.fetchAdminHealth).mockResolvedValue({
    status: 'ok',
    checked_at: '2026-10-31T12:00:00Z',
    alerts: [],
    last_sync_status: 'completed',
    last_sync_error: null,
    last_sync_at: '2026-10-31T12:00:20Z',
    last_success_at: '2026-10-31T12:00:20Z',
    anchors_failed_permanent: 0,
    anchors_stuck: 0,
    inconsistencies: 0,
  })
})
afterEach(cleanup)

describe('admin dashboard', () => {
  it('loads every number with one request, not one per card', async () => {
    vi.mocked(api.fetchAdminStats).mockResolvedValue(stats)
    render(<AdminDashboardPage />)
    expect(await screen.findByText('214')).toBeInTheDocument()
    expect(screen.getByText('Admin-managed: 9')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByTestId('stuck-anchors')).toHaveTextContent(
      '1 needs attention',
    )
    expect(screen.getAllByText('completed').length).toBeGreaterThan(0)
    expect(api.fetchAdminStats).toHaveBeenCalledTimes(1)
    // The old per-card requests (a hundred students with every version) are gone.
    expect(api.fetchAdminStudents).not.toHaveBeenCalled()
    expect(api.fetchAdminPendingVersions).not.toHaveBeenCalled()
    expect(api.fetchAdminSyncRuns).not.toHaveBeenCalled()
    expect(api.fetchAdminFlags).not.toHaveBeenCalled()
  })

  it('shows placeholders while loading, not zeros', async () => {
    vi.mocked(api.fetchAdminStats).mockReturnValue(new Promise(() => undefined))
    const { container } = render(<AdminDashboardPage />)
    expect(container.querySelectorAll('.animate-pulse').length).toBe(3)
    expect(screen.queryByText('0')).toBeNull()
  })

  it('says so and retries when the numbers cannot be loaded', async () => {
    vi.mocked(api.fetchAdminStats)
      .mockRejectedValueOnce(new Error('Failed to load dashboard metrics: 503'))
      .mockResolvedValueOnce(stats)
    render(<AdminDashboardPage />)
    expect(
      await screen.findByText('Failed to load dashboard metrics: 503'),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(screen.getByText('214')).toBeInTheDocument())
    expect(api.fetchAdminStats).toHaveBeenCalledTimes(2)
  })

  describe('Trigger Sync feedback', () => {
    const run = async () => {
      vi.mocked(api.fetchAdminStats).mockResolvedValue(stats)
      vi.spyOn(window, 'alert').mockImplementation(() => undefined)
      render(
        <AdminFeedback>
          <AdminDashboardPage />
        </AdminFeedback>,
      )
      await screen.findByText('214')
      fireEvent.click(screen.getByRole('button', { name: 'Trigger Sync' }))
    }
    const toastWith = async (title: string) =>
      (await screen.findAllByTestId('toast')).find((el) =>
        el.textContent?.includes(title),
      )

    it('confirms a finished sync with a success toast', async () => {
      vi.mocked(api.triggerAdminSync).mockResolvedValue({
        status: 'completed',
        rows_read: 12,
        versions_created: 2,
        error: null,
      })
      await run()
      const toast = await toastWith('Sync finished')
      expect(toast).toHaveAttribute('data-type', 'success')
      expect(toast).toHaveTextContent('Rows read: 12, new versions created: 2')
      expect(window.alert).not.toHaveBeenCalled()
    })

    it('warns in a toast when another sync is already running', async () => {
      vi.mocked(api.triggerAdminSync).mockResolvedValue({
        status: 'skipped',
        rows_read: 0,
        versions_created: 0,
        error: null,
      })
      await run()
      const toast = await toastWith('Sync skipped')
      expect(toast).toHaveAttribute('data-type', 'warning')
      expect(toast).toHaveTextContent('another sync is already running')
    })

    it('shows a failed sync as an error toast', async () => {
      vi.mocked(api.triggerAdminSync).mockResolvedValue({
        status: 'failed',
        rows_read: 3,
        versions_created: 0,
        error: 'sheet_unavailable',
      })
      await run()
      const toast = await toastWith('Sync failed')
      expect(toast).toHaveAttribute('data-type', 'error')
      expect(toast).toHaveTextContent('sheet_unavailable')
    })

    it('shows a network error as an error toast, not a browser popup', async () => {
      vi.mocked(api.triggerAdminSync).mockRejectedValue(
        new Error('Failed to trigger sync: Bad Gateway'),
      )
      await run()
      const toast = await toastWith('Sync failed')
      expect(toast).toHaveTextContent('Failed to trigger sync: Bad Gateway')
      expect(window.alert).not.toHaveBeenCalled()
    })
  })
})
