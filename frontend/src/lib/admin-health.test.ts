import { describe, expect, it } from 'vitest'

import { alertLink, alertReason, explainSyncReason } from '@/lib/admin-health'
import type { AdminHealthAlert } from '@/lib/api/admin'

const make = (
  code: AdminHealthAlert['code'],
  reason: string | null = null,
): AdminHealthAlert => ({
  code,
  severity: 'critical',
  message: 'm',
  reason,
  count: null,
})

describe('explainSyncReason', () => {
  it('explains known codes and passes unknown ones through', () => {
    expect(explainSyncReason('sheet_unavailable')).toMatch(/Google Sheet/)
    expect(explainSyncReason('stale_lock')).toMatch(/hung/)
    expect(explainSyncReason('other')).toBe('other')
  })
})

describe('alertReason', () => {
  it('reads sync reasons for a failed sync and anchor reasons for anchors', () => {
    expect(alertReason(make('sync_failed', 'sync_failed'))).toMatch(
      /crashed.*\(sync_failed\)/,
    )
    expect(alertReason(make('anchors_stuck', 'insufficient_funds'))).toMatch(
      /faucet.*\(insufficient_funds\)/,
    )
  })
  it('is null without a reason and bare for an unknown one', () => {
    expect(alertReason(make('sync_failed'))).toBeNull()
    expect(alertReason(make('anchors_stuck', 'rpc_error: x'))).toBe(
      'rpc_error: x',
    )
  })
})

describe('alertLink', () => {
  it('points at the page that can fix it', () => {
    expect(alertLink(make('sync_stale'))?.href).toBe('/admin/sync')
    expect(alertLink(make('anchors_failed_permanent'))?.href).toBe(
      '/admin/anchors',
    )
    expect(alertLink(make('inconsistencies'))).toBeNull()
  })
})
