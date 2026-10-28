'use client'

import { useState } from 'react'

import { PrimaryButton } from '@/components/book'
import { signInWithGoogle } from '@/lib/supabase/client'

export function SignInButton({
  label,
  unavailable,
  tone = 'gold',
}: {
  label: string
  unavailable: string
  tone?: 'gold' | 'navy'
}) {
  const [notice, setNotice] = useState<string | null>(null)

  async function onClick() {
    setNotice(null)
    try {
      const result = await signInWithGoogle()
      if (result === 'not_configured') setNotice(unavailable)
    } catch {
      setNotice(unavailable)
    }
  }

  return (
    <div className={tone === 'gold' ? 'sign-in cover-sign-in' : 'sign-in'}>
      <PrimaryButton type="button" tone={tone} onClick={() => void onClick()}>
        {label}
      </PrimaryButton>
      {notice ? (
        <p
          role="alert"
          className={tone === 'gold' ? 'cover-alert' : 'page-alert'}
        >
          {notice}
        </p>
      ) : null}
    </div>
  )
}
