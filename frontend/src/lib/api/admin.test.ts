import { describe, expect, it } from 'vitest'

import {
  adminErrorMessage,
  awardSyncNotice,
  parseAwardStudents,
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
