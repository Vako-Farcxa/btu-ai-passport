'use client'

import { useCallback, useEffect, useState } from 'react'

import { getMyFlags, markMyFlagsSeen, type StudentFlag } from '@/lib/api/flags'
import { readAccessToken } from '@/lib/supabase/client'

export type FlagsState = {
  flags: StudentFlag[]
  unread: number
  failed: boolean
  reload: () => Promise<void>
  markSeen: () => Promise<void>
}

/** The signed-in student's flags. Pass enabled=false until the passport has loaded. */
export function useMyFlags(enabled: boolean): FlagsState {
  const [flags, setFlags] = useState<StudentFlag[]>([])
  const [unread, setUnread] = useState(0)
  const [failed, setFailed] = useState(false)

  const [version, setVersion] = useState(0)
  const reload = useCallback(async () => setVersion((value) => value + 1), [])

  const markSeen = useCallback(async () => {
    try {
      const token = await readAccessToken()
      if (!token) return
      const body = await markMyFlagsSeen(token)
      setFlags(body.flags)
      setUnread(body.unread)
    } catch {
      // The dot stays; the next visit tries again.
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    let ignore = false
    async function load() {
      try {
        const token = await readAccessToken()
        if (!token) return
        const body = await getMyFlags(token)
        if (ignore) return
        setFlags(body.flags)
        setUnread(body.unread)
        setFailed(false)
      } catch {
        if (!ignore) setFailed(true)
      }
    }
    void load()
    return () => {
      ignore = true
    }
  }, [enabled, version])

  return { flags, unread, failed, reload, markSeen }
}
