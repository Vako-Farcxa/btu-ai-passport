import { beforeEach, describe, expect, it, vi } from 'vitest'

const server = vi.hoisted(() => ({ createSupabaseServer: vi.fn() }))
vi.mock('@/lib/supabase/server', () => server)

import { GET } from './route'

const exchangeCodeForSession = vi.fn()

beforeEach(() => {
  exchangeCodeForSession.mockReset()
  server.createSupabaseServer.mockReset()
  server.createSupabaseServer.mockResolvedValue({
    auth: { exchangeCodeForSession },
  })
})

function request(path: string, cookie?: string) {
  return new Request(`https://passport.example${path}`, {
    headers: cookie ? { cookie } : {},
  })
}

describe('the sign-in callback', () => {
  it('exchanges the code for a session and returns to the saved page', async () => {
    const response = await GET(
      request('/auth/callback?code=abc', 'post_login_next=%2Fadmin%2Fflags'),
    )
    expect(exchangeCodeForSession).toHaveBeenCalledWith('abc')
    expect(response.status).toBe(307)
    expect(response.headers.get('location')).toBe(
      'https://passport.example/admin/flags',
    )
  })

  it('goes to the passport page when no page was saved', async () => {
    const response = await GET(request('/auth/callback?code=abc'))
    expect(response.headers.get('location')).toBe(
      'https://passport.example/passport',
    )
  })

  it('does not call Supabase without a code', async () => {
    await GET(request('/auth/callback'))
    expect(server.createSupabaseServer).not.toHaveBeenCalled()
  })

  it('still redirects when Supabase is not configured', async () => {
    server.createSupabaseServer.mockResolvedValue(null)
    const response = await GET(request('/auth/callback?code=abc'))
    expect(response.headers.get('location')).toBe(
      'https://passport.example/passport',
    )
  })

  it.each([
    '//evil.example',
    '%2F%2Fevil.example',
    'https%3A%2F%2Fevil.example',
    '%2F%5Cevil.example',
    'javascript%3Aalert(1)',
  ])('never leaves the site for a saved value of %s', async (saved) => {
    const response = await GET(
      request('/auth/callback?code=abc', `post_login_next=${saved}`),
    )
    expect(new URL(response.headers.get('location') ?? '').origin).toBe(
      'https://passport.example',
    )
    expect(response.headers.get('location')).toBe(
      'https://passport.example/passport',
    )
  })

  it('clears the saved-page cookie, with Secure on https', async () => {
    const response = await GET(
      request('/auth/callback?code=abc', 'post_login_next=%2Fpassport'),
    )
    const cookie = response.headers.get('set-cookie') ?? ''
    expect(cookie).toContain('post_login_next=;')
    expect(cookie).toMatch(/Max-Age=0/i)
    expect(cookie).toMatch(/Secure/i)
    expect(cookie).toMatch(/SameSite=lax/i)
  })
})
