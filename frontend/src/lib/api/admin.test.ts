import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  adminErrorMessage,
  describeSyncResult,
  fetchAdminHealth,
  awardSyncNotice,
  parseAwardStudents,
  restoreAdminStudent,
  revokeAdminVersion,
  unrevokeAdminVersion,
  type AdminAwardResponse,
} from '@/lib/api/admin'

describe('parseAwardStudents', () => {
  it('reads one email per line', () => {
    expect(parseAwardStudents('a@btu.edu.ge\n\n  b@btu.edu.ge  ')).toEqual([
      { email: 'a@btu.edu.ge', first_name: '', last_name: '' },
      { email: 'b@btu.edu.ge', first_name: '', last_name: '' },
    ])
  })

  it('reads a name after the email', () => {
    expect(
      parseAwardStudents('nino@btu.edu.ge, Nino Beridze Kapanadze'),
    ).toEqual([
      {
        email: 'nino@btu.edu.ge',
        first_name: 'Nino',
        last_name: 'Beridze Kapanadze',
      },
    ])
  })

  it('splits several emails on one line', () => {
    expect(parseAwardStudents('a@btu.edu.ge; b@btu.edu.ge')).toHaveLength(2)
  })

  it('keeps a line without an email so the server can reject it', () => {
    expect(parseAwardStudents('Nino')).toEqual([
      { email: 'Nino', first_name: '', last_name: '' },
    ])
  })
})

describe('adminErrorMessage', () => {
  it('explains known codes and passes unknown ones through', () => {
    expect(adminErrorMessage('skill_name_taken')).toMatch(/already exists/)
    expect(adminErrorMessage('boom')).toBe('boom')
  })
})

describe('awardSyncNotice', () => {
  const response = (
    status: 'completed' | 'skipped' | 'failed',
    error: string | null,
  ): AdminAwardResponse => ({
    rows: [],
    sync_result: { status, rows_read: 0, versions_created: 0, error },
  })

  it('explains a sync skipped because another one is running', () => {
    expect(awardSyncNotice(response('skipped', 'sync_in_progress'))).toBe(
      'Another sync is running, your rows are saved and will sync shortly.',
    )
  })

  it('explains a failed sync and says nothing when all is well', () => {
    expect(awardSyncNotice(response('failed', 'sync_failed'))).toMatch(
      /next scheduled sync/,
    )
    expect(awardSyncNotice(response('completed', null))).toBeNull()
    expect(awardSyncNotice(response('skipped', null))).toBeNull()
  })
})

describe('describeSyncResult', () => {
  it('reports a completed run', () => {
    const notice = describeSyncResult({
      status: 'completed',
      rows_read: 5,
      versions_created: 2,
    })
    expect(notice.kind).toBe('success')
    expect(notice.text).toContain('completed')
  })

  it('reports a skipped run as a warning, not a success', () => {
    const notice = describeSyncResult({
      status: 'skipped',
      rows_read: 0,
      versions_created: 0,
    })
    expect(notice.kind).toBe('warning')
    expect(notice.text).not.toContain('completed')
  })

  it('reports a failed run with its error', () => {
    const notice = describeSyncResult({
      status: 'failed',
      rows_read: 0,
      versions_created: 0,
      error: 'sync_failed',
    })
    expect(notice.kind).toBe('error')
    expect(notice.text).toContain('sync_failed')
  })
})

vi.mock('@/lib/supabase/client', () => ({ readAccessToken: async () => 'tok' }))

describe('revocation calls', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('posts to the restore, revoke and unrevoke routes with the admin token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 })
    vi.stubGlobal('fetch', fetchMock)
    await restoreAdminStudent('BTU-ABC')
    await revokeAdminVersion('v-1')
    await unrevokeAdminVersion('v-1')
    const calls = fetchMock.mock.calls.map(([url, init]) => [
      url,
      init.method,
      init.headers.Authorization,
    ])
    expect(calls).toEqual([
      [
        'http://localhost:8000/admin/students/BTU-ABC/restore',
        'POST',
        'Bearer tok',
      ],
      ['http://localhost:8000/admin/versions/v-1/revoke', 'POST', 'Bearer tok'],
      [
        'http://localhost:8000/admin/versions/v-1/unrevoke',
        'POST',
        'Bearer tok',
      ],
    ])
  })

  it('turns an API error code into a plain sentence', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({ code: 'version_already_revoked' }),
      }),
    )
    await expect(revokeAdminVersion('v-1')).rejects.toThrow(
      'This version is already revoked.',
    )
  })

  it('explains the new error codes', () => {
    for (const code of [
      'student_archived',
      'student_not_deleted',
      'version_already_revoked',
      'version_not_revoked',
      'version_not_found',
      'sync_stale',
      'snapshot_mismatch',
    ]) {
      expect(adminErrorMessage(code)).not.toBe(code)
    }
  })
})

describe('fetchAdminHealth', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('asks the admin health route with the admin token and no cache', async () => {
    const body = { status: 'ok', alerts: [] }
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 200, json: async () => body })
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchAdminHealth()).resolves.toEqual(body)
    const [url, init] = fetchMock.mock.calls[0] as [
      string,
      { headers: Record<string, string>; cache: string },
    ]
    expect(url).toBe('http://localhost:8000/admin/health')
    expect(init.headers.Authorization).toBe('Bearer tok')
    expect(init.cache).toBe('no-store')
  })

  it('throws when the API cannot say', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue({ ok: false, status: 503, headers: new Headers() }),
    )
    await expect(fetchAdminHealth()).rejects.toThrow(/503/)
  })
})
