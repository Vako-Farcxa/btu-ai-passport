import { createBrowserClient } from '@supabase/ssr'
import type { SupabaseClient } from '@supabase/supabase-js'

import { sessionCookieOptions, writeCookie } from '@/lib/cookies'

const MOCK_COOKIE = 'passport_mock_bearer'

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const row = document.cookie
    .split('; ')
    .find((part) => part.startsWith(`${name}=`))
  const value = row?.split('=').slice(1).join('=')
  if (!value) return null
  return decodeURIComponent(value)
}

export function createSupabaseBrowser(): SupabaseClient | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  if (!url || !key) return null
  const secure =
    typeof window !== 'undefined' && window.location.protocol === 'https:'
  return createBrowserClient(url, key, {
    cookieOptions: sessionCookieOptions(secure),
  })
}

export async function readAccessToken(): Promise<string | null> {
  if (process.env.NEXT_PUBLIC_AUTH_MOCK === '1') {
    return readCookie(MOCK_COOKIE)
  }
  const client = createSupabaseBrowser()
  if (!client) return null
  try {
    const { data } = await client.auth.getSession()
    return data.session?.access_token ?? null
  } catch {
    return null
  }
}

export const POST_LOGIN_COOKIE = 'post_login_next'

export async function signInWithGoogle(
  next?: string,
): Promise<'started' | 'not_configured'> {
  const client = createSupabaseBrowser()
  if (!client) return 'not_configured'
  if (next) {
    // The redirect URL stays exactly as Supabase allows it. The callback route reads
    // this short-lived cookie to send the user back where they started.
    writeCookie(POST_LOGIN_COOKIE, encodeURIComponent(next), 600)
  }
  const { error } = await client.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: `${window.location.origin}/auth/callback`,
      queryParams: { hd: 'btu.edu.ge' },
    },
  })
  if (error) throw error
  return 'started'
}

export async function signOut(): Promise<void> {
  const client = createSupabaseBrowser()
  if (client) await client.auth.signOut()
}
