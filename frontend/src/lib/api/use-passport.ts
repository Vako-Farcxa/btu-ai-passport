'use client'

import { useEffect, useState } from 'react'

import {
  getMyPassport,
  PassportRequestError,
  type PassportErrorCode,
  type PassportResponse,
} from '@/lib/api/passport'
import { readAccessToken } from '@/lib/supabase/client'

export type PassportState =
  | { kind: 'loading' }
  | { kind: 'signed_out' }
  | { kind: 'error'; code: PassportErrorCode; retryAfter?: number | null }
  | { kind: 'ready'; body: PassportResponse }

export function useMyPassport(): PassportState {
  const [state, setState] = useState<PassportState>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const token = await readAccessToken()
        if (!token) {
          if (!cancelled) setState({ kind: 'signed_out' })
          return
        }
        const body = await getMyPassport(token)
        if (!cancelled) setState({ kind: 'ready', body })
      } catch (error) {
        if (cancelled) return
        if (error instanceof PassportRequestError) {
          setState({
            kind: 'error',
            code: error.code,
            retryAfter: error.retryAfter,
          })
          return
        }
        setState({ kind: 'error', code: 'error' })
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  return state
}
