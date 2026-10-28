import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as api from '@/lib/api/admin'

import AdminStudentDetailPage from './page'

vi.mock('next/navigation', () => ({
  useParams: () => ({ passport_id: 'BTU-ABC' }),
}))
vi.mock('@/lib/api/admin', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api/admin')>('@/lib/api/admin')
  return { ...actual, fetchAdminStudent: vi.fn() }
})

const version = (n: number, code: string) => ({
  id: `v${n}`,
  version_number: n,
  holder_name: 'Nino Beridze',
  verification_code: code,
  anchor_status: 'confirmed',
  tx_hash: null,
  issued_at: '2026-10-28T10:00:00Z',
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
    render(<AdminStudentDetailPage />)
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
