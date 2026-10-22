'use client'

import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { signInWithGoogle } from '@/lib/supabase/client'

export function SignInButton({
  label,
  unavailable,
}: {
  label: string
  unavailable: string
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
    <div className="flex flex-col items-start gap-3">
      <Button
        type="button"
        onClick={() => void onClick()}
        className="h-11 w-fit px-4"
      >
        {label}
      </Button>
      {notice ? <p role="alert">{notice}</p> : null}
    </div>
  )
}
