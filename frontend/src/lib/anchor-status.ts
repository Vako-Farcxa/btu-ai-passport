// How the admin pages describe the state of a version's blockchain anchor.
// The public never sees these: the verify page shows one "pending" state for all of them.

export type AnchorStatus =
  'pending' | 'retrying' | 'confirmed' | 'failed_permanent'

const LABELS: Record<AnchorStatus, string> = {
  pending: 'Pending',
  retrying: 'Retrying',
  confirmed: 'Confirmed',
  failed_permanent: 'Needs attention',
}

export function anchorStatusLabel(status: AnchorStatus): string {
  return LABELS[status]
}

export function anchorBadgeClasses(status: AnchorStatus): string {
  switch (status) {
    case 'confirmed':
      return 'bg-emerald-50 text-emerald-700 border border-emerald-200'
    case 'pending':
      return 'bg-amber-50 text-amber-700 border border-amber-200'
    case 'retrying':
      return 'bg-orange-50 text-orange-700 border border-orange-200'
    case 'failed_permanent':
      return 'bg-rose-50 text-rose-700 border border-rose-200'
  }
}

/** True when an admin can usefully press "Retry anchoring". */
export function canRetryAnchor(status: AnchorStatus): boolean {
  return status === 'retrying' || status === 'failed_permanent'
}

const ERRORS: Record<string, string> = {
  rpc_unreachable:
    'The blockchain node could not be reached. It retries by itself.',
  insufficient_funds:
    'The issuer wallet has no test MATIC left for gas. Top it up from the Amoy faucet. It retries by itself.',
  gas_price_too_high:
    'Network fees are above the safety limit. It retries by itself when they drop.',
  reverted: 'The transaction was mined but the contract reverted it.',
  nonce_too_low: 'The node said the transaction number was already used.',
  replacement_underpriced:
    'The node refused the higher-fee replacement. The next try offers more.',
  already_known: 'The node already has this transaction.',
  already_anchored: 'The contract says this code is already anchored.',
  stuck_max_attempts:
    'The transaction stayed stuck through every attempt. Press Retry anchoring.',
  max_attempts:
    'Every automatic attempt failed. Check the error, then press Retry anchoring.',
  slot_conflict:
    'The contract already holds different content for this code, so it can never be anchored here. Check the Sheet and re-issue the passport.',
  anchored_tx_unknown:
    'The hash is already on the chain, but its transaction could not be found. Look it up on Polygonscan.',
  wrong_chain: 'The configured RPC is not Polygon Amoy.',
  wrong_sender:
    'The configured wallet is not the contract issuer, so it cannot anchor.',
}

/** A plain sentence for a stored error code, or the code itself when it is not known. */
export function explainAnchorError(code: string | null | undefined): string {
  if (!code) return ''
  return ERRORS[code] ?? code
}

/** What to tell the admin after they pressed "Retry anchoring". */
export function retryMessage(result: { status: string; error?: string }): {
  kind: 'success' | 'warning' | 'error'
  text: string
} {
  if (result.status === 'confirmed') {
    return { kind: 'success', text: 'Anchored and confirmed on Polygon Amoy.' }
  }
  if (result.status === 'no_chain_configured') {
    return {
      kind: 'error',
      text: 'The API has no blockchain settings (RPC, contract, key), so nothing can be sent.',
    }
  }
  if (result.status === 'failed_permanent') {
    const why = explainAnchorError(result.error)
    return {
      kind: 'error',
      text: why ? `Still failing. ${why}` : 'Still failing.',
    }
  }
  const why = explainAnchorError(result.error)
  return {
    kind: 'warning',
    text: why
      ? `Not confirmed yet. ${why}`
      : 'The transaction was sent and is waiting to be mined. It is checked again every few minutes.',
  }
}
