import { NextResponse } from 'next/server'

import { safeNext } from '@/lib/safe-next'
import { createSupabaseServer } from '@/lib/supabase/server'

const POST_LOGIN_COOKIE = 'post_login_next'

export async function GET(request: Request) {
  const url = new URL(request.url)
  const code = url.searchParams.get('code')
  if (code) {
    const supabase = await createSupabaseServer()
    if (supabase) await supabase.auth.exchangeCodeForSession(code)
  }
  const cookie = request.headers
    .get('cookie')
    ?.split('; ')
    .find((part) => part.startsWith(`${POST_LOGIN_COOKIE}=`))
    ?.slice(POST_LOGIN_COOKIE.length + 1)
  let target = new URL(safeNext(cookie), url.origin)
  // Belt and braces: whatever safeNext returned, never leave this site.
  if (target.origin !== url.origin) target = new URL('/passport', url.origin)
  const response = NextResponse.redirect(target)
  response.cookies.set(POST_LOGIN_COOKIE, '', {
    path: '/',
    maxAge: 0,
    sameSite: 'lax',
    secure: url.protocol === 'https:',
  })
  return response
}
