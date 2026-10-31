import { describe, expect, it } from 'vitest'

import {
  anchorBadgeClasses,
  anchorStatusLabel,
  canRetryAnchor,
  explainAnchorError,
  retryMessage,
  type AnchorStatus,
} from '@/lib/anchor-status'

const ALL: AnchorStatus[] = [
  'pending',
  'retrying',
  'confirmed',
  'failed_permanent',
]

describe('anchor status helpers', () => {
  it('gives every status its own label and colours', () => {
    expect(new Set(ALL.map(anchorStatusLabel)).size).toBe(4)
    expect(new Set(ALL.map(anchorBadgeClasses)).size).toBe(4)
    expect(anchorStatusLabel('failed_permanent')).toBe('Needs attention')
  })

  it('only offers a retry where it can help', () => {
    expect(ALL.filter(canRetryAnchor)).toEqual(['retrying', 'failed_permanent'])
  })

  it('explains known error codes and passes unknown ones through', () => {
    expect(explainAnchorError('slot_conflict')).toMatch(/different content/)
    expect(explainAnchorError('insufficient_funds')).toMatch(/faucet/)
    expect(explainAnchorError('snapshot_mismatch')).toMatch(
      /not sent to the chain/,
    )
    expect(explainAnchorError('rpc_error: execution reverted')).toBe(
      'rpc_error: execution reverted',
    )
    expect(explainAnchorError(null)).toBe('')
    expect(explainAnchorError(undefined)).toBe('')
  })

  it('never uses an em-dash in its sentences', () => {
    for (const code of [
      'rpc_unreachable',
      'insufficient_funds',
      'gas_price_too_high',
      'reverted',
      'stuck_max_attempts',
      'max_attempts',
      'slot_conflict',
      'anchored_tx_unknown',
      'snapshot_mismatch',
      'wrong_chain',
      'wrong_sender',
    ]) {
      expect(explainAnchorError(code)).not.toContain('\u2014')
    }
  })
})

describe('retry message', () => {
  it('celebrates a confirmed anchor', () => {
    expect(retryMessage({ status: 'confirmed' })).toMatchObject({
      kind: 'success',
    })
  })

  it('warns when the transaction is sent but not mined', () => {
    const msg = retryMessage({ status: 'pending' })
    expect(msg.kind).toBe('warning')
    expect(msg.text).toMatch(/waiting to be mined/)
  })

  it('says why a retry did not work', () => {
    const msg = retryMessage({
      status: 'failed_permanent',
      error: 'slot_conflict',
    })
    expect(msg.kind).toBe('error')
    expect(msg.text).toMatch(/Still failing/)
    expect(msg.text).toMatch(/different content/)
    expect(
      retryMessage({ status: 'retrying', error: 'rpc_unreachable' }).text,
    ).toMatch(/could not be reached/)
  })

  it('reports a missing chain configuration as an error', () => {
    expect(retryMessage({ status: 'no_chain_configured' }).kind).toBe('error')
  })
})
