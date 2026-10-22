import { NextResponse } from 'next/server'

import { createSupabaseServer } from '@/lib/supabase/server'

export async function GET(request: Request) {
  const url = new URL(request.url)
  const code = url.searchParams.get('code')
  if (code) {
    const supabase = await createSupabaseServer()
    if (supabase) await supabase.auth.exchangeCodeForSession(code)
  }
  return NextResponse.redirect(new URL('/passport', url.origin))
}
