// Plain-words help for the admin health banner (the admin panel is in English).

import type { AdminHealthAlert } from '@/lib/api/admin'
import { explainAnchorError } from '@/lib/anchor-status'

const SYNC_REASONS: Record<string, string> = {
  sheet_unavailable:
    'The Google Sheet could not be read. Check that it is still shared with the service account.',
  sheet_not_configured:
    'The Sheet settings (SHEET_ID or the Google service account) are missing on the API.',
  sync_failed: 'The sync crashed while processing rows. See the API logs.',
  sync_finish_failed:
    'The sync read the Sheet but could not record its result.',
  stale_lock: 'A previous sync hung and was released after 10 minutes.',
  unknown: 'No reason was recorded.',
}

/** A sentence for a stored sync failure code, or the code itself when it is not known. */
export function explainSyncReason(code: string): string {
  return SYNC_REASONS[code] ?? code
}

/** The reason line shown under an alert, or null when the alert has none. */
export function alertReason(alert: AdminHealthAlert): string | null {
  if (!alert.reason) return null
  const text =
    alert.code === 'sync_failed'
      ? explainSyncReason(alert.reason)
      : explainAnchorError(alert.reason)
  return text === alert.reason ? alert.reason : `${text} (${alert.reason})`
}

/** The admin page where the problem can be looked at. */
export function alertLink(
  alert: AdminHealthAlert,
): { href: string; label: string } | null {
  switch (alert.code) {
    case 'sync_failed':
    case 'sync_stale':
    case 'sync_never_succeeded':
      return { href: '/admin/sync', label: 'Open Sync Monitor' }
    case 'anchors_failed_permanent':
    case 'anchors_stuck':
      return { href: '/admin/anchors', label: 'Open Anchor Monitor' }
    default:
      return null
  }
}
