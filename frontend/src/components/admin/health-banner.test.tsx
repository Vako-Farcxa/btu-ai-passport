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

import { HealthBanner } from './health-banner'

vi.mock('@/lib/api/admin', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api/admin')>('@/lib/api/admin')
  return { ...actual, fetchAdminHealth: vi.fn() }
})

const alert = (
  code: api.AdminHealthAlert['code'],
  severity: api.AdminHealthAlert['severity'],
  message: string,
  extra: Partial<api.AdminHealthAlert> = {},
): api.AdminHealthAlert => ({
  code,
  severity,
  message,
  reason: null,
  count: null,
  ...extra,
})

const health = (
  alerts: api.AdminHealthAlert[],
  status: api.AdminHealth['status'],
): api.AdminHealth => ({
  status,
  checked_at: '2026-10-31T12:00:00Z',
  alerts,
  last_sync_status: 'completed',
  last_sync_error: null,
  last_sync_at: '2026-10-31T11:55:00Z',
  last_success_at: '2026-10-31T11:55:00Z',
  anchors_failed_permanent: 0,
  anchors_stuck: 0,
  inconsistencies: 0,
})

beforeEach(() => vi.mocked(api.fetchAdminHealth).mockReset())
afterEach(cleanup)

describe('HealthBanner', () => {
  it('shows nothing while all is well', async () => {
    vi.mocked(api.fetchAdminHealth).mockResolvedValue(health([], 'ok'))
    render(<HealthBanner />)
    await waitFor(() => expect(api.fetchAdminHealth).toHaveBeenCalled())
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(screen.queryByTestId('health-banner')).toBeNull()
  })

  it('is red for a failed sync and explains the reason code', async () => {
    vi.mocked(api.fetchAdminHealth).mockResolvedValue(
      health(
        [
          alert('sync_failed', 'critical', 'The last sync failed.', {
            reason: 'sheet_unavailable',
          }),
        ],
        'critical',
      ),
    )
    render(<HealthBanner />)
    const banner = await screen.findByTestId('health-banner')
    expect(banner).toHaveAttribute('data-severity', 'critical')
    expect(banner).toHaveAttribute('role', 'alert')
    expect(banner).toHaveClass('bg-rose-50')
    expect(screen.getByText('The last sync failed.')).toBeVisible()
    expect(screen.getByTestId('health-alert-reason')).toHaveTextContent(
      /Google Sheet could not be read.*\(sheet_unavailable\)/,
    )
    expect(
      screen.getByRole('link', { name: 'Open Sync Monitor' }),
    ).toHaveAttribute('href', '/admin/sync')
  })

  it('is amber when there are only warnings', async () => {
    vi.mocked(api.fetchAdminHealth).mockResolvedValue(
      health(
        [
          alert(
            'sync_stale',
            'warning',
            'No sync has completed for 75 minutes.',
          ),
          alert('anchors_stuck', 'warning', '2 versions are waiting.', {
            reason: 'rpc_unreachable',
            count: 2,
          }),
          alert('inconsistencies', 'warning', 'The check found 3 problems.', {
            count: 3,
          }),
        ],
        'warning',
      ),
    )
    render(<HealthBanner />)
    const banner = await screen.findByTestId('health-banner')
    expect(banner).toHaveAttribute('data-severity', 'warning')
    expect(banner).toHaveAttribute('role', 'status')
    expect(banner).toHaveClass('bg-amber-50')
    expect(banner).not.toHaveClass('bg-rose-50')
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    expect(
      within(screen.getByTestId('health-alert-anchors_stuck')).getByTestId(
        'health-alert-reason',
      ),
    ).toHaveTextContent(/blockchain node could not be reached/)
    expect(
      within(screen.getByTestId('health-alert-anchors_stuck')).getByRole(
        'link',
        { name: 'Open Anchor Monitor' },
      ),
    ).toHaveAttribute('href', '/admin/anchors')
    expect(
      within(screen.getByTestId('health-alert-inconsistencies')).queryByRole(
        'link',
      ),
    ).toBeNull()
  })

  it('is red when any alert is critical and lists every alert', async () => {
    vi.mocked(api.fetchAdminHealth).mockResolvedValue(
      health(
        [
          alert(
            'anchors_failed_permanent',
            'critical',
            '1 version needs you.',
            {
              count: 1,
            },
          ),
          alert('sync_stale', 'warning', 'No sync for 90 minutes.'),
        ],
        'critical',
      ),
    )
    render(<HealthBanner />)
    expect(await screen.findByTestId('health-banner')).toHaveAttribute(
      'data-severity',
      'critical',
    )
    expect(screen.getByTestId('health-alert-sync_stale')).toHaveAttribute(
      'data-severity',
      'warning',
    )
  })

  it('shows an unknown reason code as it is', async () => {
    vi.mocked(api.fetchAdminHealth).mockResolvedValue(
      health(
        [
          alert('sync_failed', 'critical', 'The last sync failed.', {
            reason: 'brand_new_code',
          }),
        ],
        'critical',
      ),
    )
    render(<HealthBanner />)
    expect(await screen.findByTestId('health-alert-reason')).toHaveTextContent(
      'Reason: brand_new_code',
    )
  })

  it('says so, in amber, when the health check itself fails, and retries', async () => {
    vi.mocked(api.fetchAdminHealth)
      .mockRejectedValueOnce(new Error('Failed to load system health: 503'))
      .mockResolvedValueOnce(health([], 'ok'))
    render(<HealthBanner />)
    const banner = await screen.findByTestId('health-banner')
    expect(banner).toHaveAttribute('data-severity', 'warning')
    expect(banner).toHaveTextContent('System health could not be checked.')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() =>
      expect(screen.queryByTestId('health-banner')).toBeNull(),
    )
    expect(api.fetchAdminHealth).toHaveBeenCalledTimes(2)
  })

  it('checks again on request and when refreshKey changes', async () => {
    vi.mocked(api.fetchAdminHealth).mockResolvedValue(
      health(
        [alert('sync_stale', 'warning', 'No sync for 70 minutes.')],
        'warning',
      ),
    )
    const { rerender } = render(<HealthBanner refreshKey="a" />)
    await screen.findByTestId('health-banner')
    expect(api.fetchAdminHealth).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Check again' }))
    await waitFor(() => expect(api.fetchAdminHealth).toHaveBeenCalledTimes(2))
    rerender(<HealthBanner refreshKey="b" />)
    await waitFor(() => expect(api.fetchAdminHealth).toHaveBeenCalledTimes(3))
  })
})
