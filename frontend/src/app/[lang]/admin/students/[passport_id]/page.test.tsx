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

import AdminStudentDetailPage from './page'

vi.mock('next/navigation', () => ({
  useParams: () => ({ passport_id: 'BTU-ABC' }),
}))
vi.mock('@/lib/api/admin', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api/admin')>('@/lib/api/admin')
  return {
    ...actual,
    fetchAdminStudent: vi.fn(),
    restoreAdminStudent: vi.fn(),
    revokeAdminVersion: vi.fn(),
    unrevokeAdminVersion: vi.fn(),
    retryAdminAnchor: vi.fn(),
  }
})

function renderPage() {
  return render(
    <AdminFeedback>
      <AdminStudentDetailPage />
    </AdminFeedback>,
  )
}

async function answer(name: string) {
  const dialog = await screen.findByRole('alertdialog')
  fireEvent.click(within(dialog).getByRole('button', { name }))
}

const version = (n: number, code: string) => ({
  id: `v${n}`,
  version_number: n,
  holder_name: 'Nino Beridze',
  verification_code: code,
  anchor_status: 'confirmed',
  anchor_attempts: 1,
  anchor_last_error: null as string | null,
  tx_hash: null,
  issued_at: '2026-10-28T10:00:00Z',
  revoked_at: null as string | null,
  skills: [],
})

describe('admin student detail verify links', () => {
  beforeEach(() => {
    vi.mocked(api.fetchAdminStudent).mockResolvedValue({
      email: 'nino@btu.edu.ge',
      full_name: 'Nino Beridze',
      passport_id: 'BTU-ABC',
      admin_managed: false,
      versions: [
        version(2, 'AAAA-BBBB-CCCC-DDDD'),
        version(1, 'EEEE-FFFF-GGGG-HHHH'),
      ],
    } as never)
  })
  afterEach(cleanup)

  it('opens the verify page with the version code, not the plain page', async () => {
    renderPage()
    await screen.findByText(/Verify Code/)
    const hrefs = screen
      .getAllByRole('link')
      .map((link) => link.getAttribute('href'))
      .filter((href) => href?.startsWith('/verify'))
    expect(hrefs).toContain('/verify?code=AAAA-BBBB-CCCC-DDDD')
    expect(hrefs).toContain('/verify?code=EEEE-FFFF-GGGG-HHHH')
    expect(hrefs).not.toContain('/verify')
  })
})

describe('admin student detail revocation controls', () => {
  const detail = (
    extra: object,
    versions = [version(1, 'AAAA-BBBB-CCCC-DDDD')],
  ) =>
    ({
      email: 'nino@btu.edu.ge',
      full_name: 'Nino Beridze',
      passport_id: 'BTU-ABC',
      admin_managed: false,
      deleted_at: null,
      versions,
      ...extra,
    }) as never

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('shows no archived banner for an active student', async () => {
    vi.mocked(api.fetchAdminStudent).mockResolvedValue(detail({}))
    renderPage()
    await screen.findByText(/Verify Code/)
    expect(screen.queryByTestId('archived-banner')).toBeNull()
  })

  it('marks an archived student and restores them after a confirm', async () => {
    vi.mocked(api.fetchAdminStudent)
      .mockResolvedValueOnce(detail({ deleted_at: '2026-10-30T10:00:00Z' }))
      .mockResolvedValue(detail({}))
    vi.mocked(api.restoreAdminStudent).mockResolvedValue(undefined)
    renderPage()
    const banner = await screen.findByTestId('archived-banner')
    expect(banner).toHaveTextContent(/Revoked/)
    fireEvent.click(screen.getByRole('button', { name: 'Restore student' }))
    await answer('Restore student')
    await waitFor(() =>
      expect(api.restoreAdminStudent).toHaveBeenCalledWith('BTU-ABC'),
    )
    await waitFor(() =>
      expect(screen.queryByTestId('archived-banner')).toBeNull(),
    )
  })

  it('does nothing when the admin cancels the confirm', async () => {
    vi.mocked(api.fetchAdminStudent).mockResolvedValue(
      detail({ deleted_at: '2026-10-30T10:00:00Z' }),
    )
    renderPage()
    await screen.findByTestId('archived-banner')
    fireEvent.click(screen.getByRole('button', { name: 'Restore student' }))
    await answer('Cancel')
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument(),
    )
    expect(api.restoreAdminStudent).not.toHaveBeenCalled()
  })

  it('cancels with Escape and puts focus back on the button that opened it', async () => {
    vi.mocked(api.fetchAdminStudent).mockResolvedValue(detail({}))
    renderPage()
    const trigger = await screen.findByRole('button', {
      name: 'Revoke version',
    })
    trigger.focus()
    fireEvent.click(trigger)
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveAccessibleName('Revoke version 1?')
    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: 'Escape',
    })
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument(),
    )
    expect(api.revokeAdminVersion).not.toHaveBeenCalled()
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('styles revoking as a danger action and restoring as a normal one', async () => {
    vi.mocked(api.fetchAdminStudent).mockResolvedValue(
      detail({}, [
        { ...version(1, 'AAAA-BBBB-CCCC-DDDD'), revoked_at: null },
        {
          ...version(2, 'EEEE-FFFF-GGGG-HHHH'),
          revoked_at: '2026-10-30T10:00:00Z',
        },
      ]),
    )
    renderPage()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Revoke version' }),
    )
    let dialog = await screen.findByRole('alertdialog')
    expect(
      within(dialog).getByRole('button', { name: 'Revoke version' }),
    ).toHaveAttribute('data-variant', 'danger')
    expect(dialog.textContent).not.toMatch(/\u2014|\u2013/)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Restore version' }))
    dialog = await screen.findByRole('alertdialog')
    expect(
      within(dialog).getByRole('button', { name: 'Restore version' }),
    ).toHaveAttribute('data-variant', 'default')
  })

  it('revokes a version and shows a revoked version with a restore button', async () => {
    vi.mocked(api.fetchAdminStudent)
      .mockResolvedValueOnce(detail({}))
      .mockResolvedValue(
        detail({}, [
          {
            ...version(1, 'AAAA-BBBB-CCCC-DDDD'),
            revoked_at: '2026-10-30T10:00:00Z',
          },
        ]),
      )
    vi.mocked(api.revokeAdminVersion).mockResolvedValue(undefined)
    renderPage()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Revoke version' }),
    )
    await answer('Revoke version')
    await waitFor(() =>
      expect(api.revokeAdminVersion).toHaveBeenCalledWith('v1'),
    )
    expect(await screen.findByText(/^REVOKED/)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Restore version' }),
    ).toBeInTheDocument()
  })

  it('shows the error when the action fails', async () => {
    vi.mocked(api.fetchAdminStudent).mockResolvedValue(detail({}))
    vi.mocked(api.revokeAdminVersion).mockRejectedValue(
      new Error('This version is already revoked.'),
    )
    renderPage()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Revoke version' }),
    )
    await answer('Revoke version')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This version is already revoked.',
    )
  })
})

describe('admin student detail anchoring', () => {
  const detail = (versions: object[]) =>
    ({
      email: 'nino@btu.edu.ge',
      full_name: 'Nino Beridze',
      passport_id: 'BTU-ABC',
      admin_managed: false,
      deleted_at: null,
      versions,
    }) as never

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('shows nothing extra for a confirmed version', async () => {
    vi.mocked(api.fetchAdminStudent).mockResolvedValue(
      detail([version(1, 'AAAA-BBBB-CCCC-DDDD')]),
    )
    renderPage()
    await screen.findByText(/Verify Code/)
    expect(screen.queryByTestId('anchor-detail')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Retry anchoring' })).toBeNull()
  })

  it('explains a failed anchor and retries it', async () => {
    const failed = {
      ...version(1, 'AAAA-BBBB-CCCC-DDDD'),
      anchor_status: 'failed_permanent',
      anchor_attempts: 6,
      anchor_last_error: 'insufficient_funds',
    }
    vi.mocked(api.fetchAdminStudent)
      .mockResolvedValueOnce(detail([failed]))
      .mockResolvedValue(detail([version(1, 'AAAA-BBBB-CCCC-DDDD')]))
    vi.mocked(api.retryAdminAnchor).mockResolvedValue({ status: 'confirmed' })
    renderPage()
    const box = await screen.findByTestId('anchor-detail')
    expect(box).toHaveTextContent('Anchoring needs attention')
    expect(box).toHaveTextContent('Attempts so far: 6')
    expect(box).toHaveTextContent(/no test MATIC/)
    expect(screen.getByText(/Anchor: Needs attention/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry anchoring' }))
    await waitFor(() => expect(api.retryAdminAnchor).toHaveBeenCalledWith('v1'))
    expect(await screen.findByTestId('anchor-notice')).toHaveTextContent(
      'Anchored and confirmed',
    )
    await waitFor(() =>
      expect(screen.queryByTestId('anchor-detail')).toBeNull(),
    )
  })

  it('offers no retry while a first transaction is still being mined', async () => {
    vi.mocked(api.fetchAdminStudent).mockResolvedValue(
      detail([
        {
          ...version(1, 'AAAA-BBBB-CCCC-DDDD'),
          anchor_status: 'pending',
          anchor_attempts: 1,
        },
      ]),
    )
    renderPage()
    expect(await screen.findByTestId('anchor-detail')).toHaveTextContent(
      'Waiting for the blockchain',
    )
    expect(screen.queryByRole('button', { name: 'Retry anchoring' })).toBeNull()
  })

  it('shows the API error when the retry is refused', async () => {
    vi.mocked(api.fetchAdminStudent).mockResolvedValue(
      detail([
        {
          ...version(1, 'AAAA-BBBB-CCCC-DDDD'),
          anchor_status: 'retrying',
          anchor_attempts: 2,
        },
      ]),
    )
    vi.mocked(api.retryAdminAnchor).mockRejectedValue(
      new Error('Another anchoring run is in progress. Try again in a minute.'),
    )
    renderPage()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Retry anchoring' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Another anchoring run is in progress',
    )
  })
})
