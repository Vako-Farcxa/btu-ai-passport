import { createBrowserClient } from '@supabase/ssr'
import type { SupabaseClient } from '@supabase/supabase-js'

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
  return createBrowserClient(url, key)
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

export async function signInWithGoogle(): Promise<
  'started' | 'not_configured'
> {
  const client = createSupabaseBrowser()
  if (!client) return 'not_configured'
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
