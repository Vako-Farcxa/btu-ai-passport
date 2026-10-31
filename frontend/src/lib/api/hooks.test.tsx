import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PassportRequestError } from '@/lib/api/passport'
import { useMyFlags } from '@/lib/api/use-flags'
import { useMyPassport } from '@/lib/api/use-passport'

const token = vi.hoisted(() => ({ value: 'tok' as string | null }))
vi.mock('@/lib/supabase/client', () => ({
  readAccessToken: async () => token.value,
}))
const passportApi = vi.hoisted(() => ({ getMyPassport: vi.fn() }))
vi.mock('@/lib/api/passport', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api/passport')>(
      '@/lib/api/passport',
    )
  return { ...actual, getMyPassport: passportApi.getMyPassport }
})
const flagsApi = vi.hoisted(() => ({
  getMyFlags: vi.fn(),
  markMyFlagsSeen: vi.fn(),
}))
vi.mock('@/lib/api/flags', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api/flags')>('@/lib/api/flags')
  return { ...actual, ...flagsApi }
})

beforeEach(() => {
  token.value = 'tok'
  passportApi.getMyPassport.mockReset()
  flagsApi.getMyFlags.mockReset()
  flagsApi.markMyFlagsSeen.mockReset()
})
afterEach(cleanup)

describe('useMyPassport', () => {
  it('starts loading, then holds the passport', async () => {
    passportApi.getMyPassport.mockResolvedValue({ passport: null })
    const { result } = renderHook(() => useMyPassport())
    expect(result.current).toEqual({ kind: 'loading' })
    await waitFor(() => expect(result.current.kind).toBe('ready'))
    expect(passportApi.getMyPassport).toHaveBeenCalledWith('tok')
  })

  it('is signed out without a session and never calls the API', async () => {
    token.value = null
    const { result } = renderHook(() => useMyPassport())
    await waitFor(() => expect(result.current).toEqual({ kind: 'signed_out' }))
    expect(passportApi.getMyPassport).not.toHaveBeenCalled()
  })

  it('keeps the error code and the wait from a refused request', async () => {
    passportApi.getMyPassport.mockRejectedValue(
      new PassportRequestError('rate_limited', 30),
    )
    const { result } = renderHook(() => useMyPassport())
    await waitFor(() =>
      expect(result.current).toEqual({
        kind: 'error',
        code: 'rate_limited',
        retryAfter: 30,
      }),
    )
  })

  it('reports any other failure as a plain error', async () => {
    passportApi.getMyPassport.mockRejectedValue(new TypeError('network'))
    const { result } = renderHook(() => useMyPassport())
    await waitFor(() =>
      expect(result.current).toEqual({ kind: 'error', code: 'error' }),
    )
  })

  it('ignores a late answer after unmount', async () => {
    let finish: (value: unknown) => void = () => undefined
    passportApi.getMyPassport.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    const { result, unmount } = renderHook(() => useMyPassport())
    await waitFor(() => expect(passportApi.getMyPassport).toHaveBeenCalled())
    unmount()
    await act(async () => finish({ passport: null }))
    expect(result.current).toEqual({ kind: 'loading' })
  })
})

describe('useMyFlags', () => {
  const flag = { id: 'f1', version: 1, unread: true }

  it('does nothing until it is enabled', async () => {
    const { result, rerender } = renderHook(({ on }) => useMyFlags(on), {
      initialProps: { on: false },
    })
    expect(flagsApi.getMyFlags).not.toHaveBeenCalled()
    flagsApi.getMyFlags.mockResolvedValue({ flags: [flag], unread: 1 })
    rerender({ on: true })
    await waitFor(() => expect(result.current.flags).toEqual([flag]))
    expect(result.current.unread).toBe(1)
    expect(result.current.failed).toBe(false)
  })

  it('marks the list as failed when the request fails, and recovers on reload', async () => {
    flagsApi.getMyFlags.mockRejectedValueOnce(new Error('down'))
    const { result } = renderHook(() => useMyFlags(true))
    await waitFor(() => expect(result.current.failed).toBe(true))

    flagsApi.getMyFlags.mockResolvedValueOnce({ flags: [flag], unread: 1 })
    await act(async () => result.current.reload())
    await waitFor(() => expect(result.current.failed).toBe(false))
    expect(result.current.flags).toEqual([flag])
  })

  it('stays empty without a session', async () => {
    token.value = null
    const { result } = renderHook(() => useMyFlags(true))
    await act(async () => result.current.markSeen())
    expect(flagsApi.getMyFlags).not.toHaveBeenCalled()
    expect(flagsApi.markMyFlagsSeen).not.toHaveBeenCalled()
    expect(result.current.flags).toEqual([])
  })

  it('markSeen replaces the list with the server answer and swallows a failure', async () => {
    flagsApi.getMyFlags.mockResolvedValue({ flags: [flag], unread: 1 })
    const { result } = renderHook(() => useMyFlags(true))
    await waitFor(() => expect(result.current.unread).toBe(1))

    flagsApi.markMyFlagsSeen.mockResolvedValueOnce({
      flags: [{ ...flag, unread: false }],
      unread: 0,
    })
    await act(async () => result.current.markSeen())
    expect(result.current.unread).toBe(0)

    flagsApi.markMyFlagsSeen.mockRejectedValueOnce(new Error('down'))
    await act(async () => result.current.markSeen())
    expect(result.current.unread).toBe(0)
  })
})
