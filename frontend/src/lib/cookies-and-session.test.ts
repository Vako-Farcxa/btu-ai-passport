import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cookieAttributes,
  sessionCookieOptions,
  writeCookie,
} from '@/lib/cookies'

const ssr = vi.hoisted(() => ({ createBrowserClient: vi.fn() }))
vi.mock('@supabase/ssr', () => ssr)

import {
  POST_LOGIN_COOKIE,
  createSupabaseBrowser,
  readAccessToken,
  signInWithGoogle,
  signOut,
} from '@/lib/supabase/client'

function clearCookies() {
  for (const part of document.cookie.split('; ')) {
    const name = part.split('=')[0]
    if (name) document.cookie = `${name}=; max-age=0; path=/`
  }
}

beforeEach(() => {
  clearCookies()
  ssr.createBrowserClient.mockReset()
})
afterEach(() => {
  vi.unstubAllEnvs()
  clearCookies()
})

describe('cookies', () => {
  it('writes a same-site cookie with the max age, and no Secure on http', () => {
    expect(cookieAttributes(60)).toBe('path=/; max-age=60; SameSite=Lax')
    writeCookie('passport_locale', 'ka', 60)
    expect(document.cookie).toContain('passport_locale=ka')
  })

  it('adds Secure when the page is served over https', () => {
    vi.stubGlobal('window', { location: { protocol: 'https:' } })
    expect(cookieAttributes(60)).toBe(
      'path=/; max-age=60; SameSite=Lax; Secure',
    )
    vi.unstubAllGlobals()
  })

  it('keeps session cookies readable by scripts', () => {
    expect(sessionCookieOptions(true)).toEqual({
      path: '/',
      sameSite: 'lax',
      secure: true,
    })
    expect(sessionCookieOptions(false)).not.toHaveProperty('httpOnly')
  })
})

describe('the browser Supabase client', () => {
  it('is null when the project is not configured', () => {
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', '')
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', '')
    expect(createSupabaseBrowser()).toBeNull()
    expect(ssr.createBrowserClient).not.toHaveBeenCalled()
  })

  it('is created with the public URL, key and script-readable cookies', () => {
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://x.supabase.co')
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'anon')
    ssr.createBrowserClient.mockReturnValue({ id: 'client' })
    expect(createSupabaseBrowser()).toEqual({ id: 'client' })
    expect(ssr.createBrowserClient).toHaveBeenCalledWith(
      'https://x.supabase.co',
      'anon',
      { cookieOptions: { path: '/', sameSite: 'lax', secure: false } },
    )
  })
})

describe('readAccessToken', () => {
  it('reads the mock cookie only when the mock is switched on', async () => {
    document.cookie = 'passport_mock_bearer=a%20b; path=/'
    vi.stubEnv('NEXT_PUBLIC_AUTH_MOCK', '1')
    expect(await readAccessToken()).toBe('a b')
    clearCookies()
    expect(await readAccessToken()).toBeNull()
  })

  it('ignores the mock cookie in a real build', async () => {
    document.cookie = 'passport_mock_bearer=sneaky; path=/'
    vi.stubEnv('NEXT_PUBLIC_AUTH_MOCK', '')
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', '')
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', '')
    expect(await readAccessToken()).toBeNull()
  })

  it('returns the session token, or null when there is no session or it throws', async () => {
    vi.stubEnv('NEXT_PUBLIC_AUTH_MOCK', '')
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://x.supabase.co')
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'anon')
    const getSession = vi.fn()
    ssr.createBrowserClient.mockReturnValue({ auth: { getSession } })

    getSession.mockResolvedValueOnce({
      data: { session: { access_token: 'real' } },
    })
    expect(await readAccessToken()).toBe('real')
    getSession.mockResolvedValueOnce({ data: { session: null } })
    expect(await readAccessToken()).toBeNull()
    getSession.mockRejectedValueOnce(new Error('storage blocked'))
    expect(await readAccessToken()).toBeNull()
  })
})

describe('signing in and out', () => {
  const configure = (auth: object) => {
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://x.supabase.co')
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'anon')
    ssr.createBrowserClient.mockReturnValue({ auth })
  }

  it('says so when sign-in is not configured', async () => {
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', '')
    vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', '')
    expect(await signInWithGoogle()).toBe('not_configured')
    await expect(signOut()).resolves.toBeUndefined()
  })

  it('starts Google sign-in limited to btu.edu.ge and remembers where to return', async () => {
    const signInWithOAuth = vi.fn().mockResolvedValue({ error: null })
    configure({ signInWithOAuth })
    expect(await signInWithGoogle('/passport')).toBe('started')
    expect(signInWithOAuth).toHaveBeenCalledWith({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
        queryParams: { hd: 'btu.edu.ge' },
      },
    })
    expect(document.cookie).toContain(`${POST_LOGIN_COOKIE}=%2Fpassport`)
  })

  it('leaves no return cookie when none was asked for, and throws provider errors', async () => {
    const signInWithOAuth = vi
      .fn()
      .mockResolvedValue({ error: new Error('provider down') })
    configure({ signInWithOAuth })
    await expect(signInWithGoogle()).rejects.toThrow('provider down')
    expect(document.cookie).not.toContain(POST_LOGIN_COOKIE)
  })

  it('signs out through the client', async () => {
    const signOutFn = vi.fn().mockResolvedValue({})
    configure({ signOut: signOutFn })
    await signOut()
    expect(signOutFn).toHaveBeenCalledOnce()
  })
})
