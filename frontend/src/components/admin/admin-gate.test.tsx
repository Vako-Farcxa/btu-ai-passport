import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminGate } from '@/components/admin/admin-gate'
import { AdminAccessError } from '@/lib/api/admin'

const readAccessToken = vi.fn<() => Promise<string | null>>()
const fetchAdminMe = vi.fn<() => Promise<{ email: string }>>()

vi.mock('@/lib/supabase/client', () => ({
  readAccessToken: () => readAccessToken(),
  signInWithGoogle: vi.fn(),
  signOut: vi.fn(),
}))
vi.mock('@/lib/api/admin', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/admin')>()),
  fetchAdminMe: () => fetchAdminMe(),
}))

beforeEach(() => {
  readAccessToken.mockReset()
  fetchAdminMe.mockReset()
})
afterEach(cleanup)

function renderGate() {
  return render(
    <AdminGate>
      <p>secret admin content</p>
    </AdminGate>,
  )
}

describe('AdminGate', () => {
  it('shows a sign-in screen and never asks the API when signed out', async () => {
    readAccessToken.mockResolvedValue(null)
    renderGate()
    expect(await screen.findByText('Admin sign-in required')).toBeVisible()
    expect(
      screen.getByRole('button', { name: 'Sign in with Google' }),
    ).toBeVisible()
    expect(screen.queryByText('secret admin content')).toBeNull()
    expect(fetchAdminMe).not.toHaveBeenCalled()
  })

  it('shows not authorized when the backend says 403', async () => {
    readAccessToken.mockResolvedValue('token')
    fetchAdminMe.mockRejectedValue(new AdminAccessError('not_authorized'))
    renderGate()
    expect(await screen.findByText('Not authorized')).toBeVisible()
    expect(screen.queryByText('secret admin content')).toBeNull()
  })

  it('sends an expired session back to sign-in', async () => {
    readAccessToken.mockResolvedValue('token')
    fetchAdminMe.mockRejectedValue(new AdminAccessError('signed_out'))
    renderGate()
    expect(await screen.findByText('Admin sign-in required')).toBeVisible()
    expect(screen.queryByText('secret admin content')).toBeNull()
  })

  it('shows nothing when the API is unreachable', async () => {
    readAccessToken.mockResolvedValue('token')
    fetchAdminMe.mockRejectedValue(new Error('network'))
    renderGate()
    expect(await screen.findByText('Could not check access')).toBeVisible()
    expect(screen.queryByText('secret admin content')).toBeNull()
  })

  it('renders the panel only after the backend confirms an admin', async () => {
    readAccessToken.mockResolvedValue('token')
    fetchAdminMe.mockResolvedValue({ email: 'admin@btu.edu.ge' })
    renderGate()
    expect(screen.queryByText('secret admin content')).toBeNull()
    await waitFor(() =>
      expect(screen.getByText('secret admin content')).toBeVisible(),
    )
  })
})
