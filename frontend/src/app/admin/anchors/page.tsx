'use client'

import Link from 'next/link'
import React, { useEffect, useState } from 'react'
import {
  fetchAdminPendingVersions,
  retryAdminAnchor,
  type AdminVersionPending,
} from '@/lib/api/admin'
import {
  anchorBadgeClasses,
  anchorStatusLabel,
  canRetryAnchor,
  explainAnchorError,
  retryMessage,
} from '@/lib/anchor-status'

export default function AdminAnchorsPage() {
  const [pending, setPending] = useState<AdminVersionPending[]>([])
  const [loading, setLoading] = useState(true)
  const [retryingId, setRetryingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<ReturnType<typeof retryMessage> | null>(
    null,
  )

  const loadPending = async () => {
    setLoading(true)
    try {
      const data = await fetchAdminPendingVersions()
      setPending(data.versions)
      setError(null)
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : 'Failed to load pending versions',
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let ignore = false
    async function init() {
      try {
        const data = await fetchAdminPendingVersions()
        if (!ignore) {
          setPending(data.versions)
          setError(null)
        }
      } catch (err: unknown) {
        if (!ignore) {
          setError(
            err instanceof Error
              ? err.message
              : 'Failed to load pending versions',
          )
        }
      } finally {
        if (!ignore) {
          setLoading(false)
        }
      }
    }
    void init()
    return () => {
      ignore = true
    }
  }, [])

  const handleRetry = async (versionId: string) => {
    try {
      setRetryingId(versionId)
      setNotice(null)
      setError(null)
      const res = await retryAdminAnchor(versionId)
      setNotice(retryMessage(res))
      await loadPending()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Retrying anchoring failed')
    } finally {
      setRetryingId(null)
    }
  }

  const attention = pending.filter(
    (item) => item.anchor_status === 'failed_permanent',
  ).length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Blockchain Anchor Monitor
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Tracks cryptographic proof anchoring on the Polygon Amoy testnet.
          </p>
        </div>
        <button
          onClick={loadPending}
          className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 transition-colors shadow-sm self-start sm:self-auto"
        >
          Refresh Queue
        </button>
      </div>

      {notice && (
        <div
          role="status"
          data-testid="anchor-notice"
          className={`p-4 rounded-xl border text-xs flex items-center justify-between ${
            notice.kind === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : notice.kind === 'warning'
                ? 'bg-amber-50 border-amber-200 text-amber-800'
                : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          <span>{notice.text}</span>
          <button
            onClick={() => setNotice(null)}
            aria-label="Dismiss"
            className="font-bold ml-4"
          >
            ✕
          </button>
        </div>
      )}

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between">
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            className="text-rose-600 font-bold ml-4"
          >
            ✕
          </button>
        </div>
      )}

      {/* Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Network Target
          </span>
          <p className="mt-1 text-sm font-bold text-slate-900">
            Polygon Amoy Testnet
          </p>
          <p className="text-xs text-slate-400 mt-1">Chain ID: 80002</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Privacy Guarantee
          </span>
          <p className="mt-1 text-sm font-bold text-slate-900">
            Zero PII On-Chain
          </p>
          <p className="text-xs text-slate-400 mt-1">
            Only content_hash & verification_id_hash
          </p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Pending Queue Size
          </span>
          <p className="mt-1 text-sm font-bold text-slate-900">
            {pending.length} versions
          </p>
          <p className="text-xs text-slate-400 mt-1">
            {attention > 0
              ? `${attention} need${attention === 1 ? 's' : ''} attention`
              : 'Checked automatically every 15 minutes'}
          </p>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
        <div className="p-6 border-b border-slate-100">
          <h2 className="text-base font-semibold text-slate-900">
            Pending & Failed Anchors
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Versions whose blockchain transaction has not yet been confirmed on
            Polygon Amoy. Stuck or dropped transactions are replaced and failed
            sends are retried automatically. Versions marked Needs attention
            stopped after the attempt limit and wait for you.
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider border-b border-slate-100">
              <tr>
                <th className="px-6 py-3 font-semibold">Student</th>
                <th className="px-6 py-3 font-semibold">Passport ID</th>
                <th className="px-6 py-3 font-semibold">Version</th>
                <th className="px-6 py-3 font-semibold">Issued Date</th>
                <th className="px-6 py-3 font-semibold">Status</th>
                <th className="px-6 py-3 font-semibold">Details</th>
                <th className="px-6 py-3 font-semibold text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td
                    colSpan={7}
                    className="px-6 py-12 text-center text-slate-400 text-xs"
                  >
                    Checking queue...
                  </td>
                </tr>
              ) : pending.length === 0 ? (
                <tr>
                  <td
                    colSpan={7}
                    className="px-6 py-12 text-center text-slate-400 text-xs"
                  >
                    All issued passport versions are fully confirmed on the
                    blockchain! 🎉
                  </td>
                </tr>
              ) : (
                pending.map((item) => (
                  <tr
                    key={item.version_id}
                    className="hover:bg-slate-50/50 transition-colors"
                  >
                    <td className="px-6 py-4 font-medium text-slate-900">
                      <Link
                        href={`/admin/students/${item.passport_id}`}
                        className="hover:text-indigo-600 transition-colors"
                      >
                        {item.holder_name}
                      </Link>
                    </td>
                    <td className="px-6 py-4 text-xs font-mono text-slate-600">
                      {item.passport_id}
                    </td>
                    <td className="px-6 py-4 text-xs font-mono font-medium text-slate-800">
                      Version {item.version_number}
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {new Date(item.issued_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 text-xs">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${anchorBadgeClasses(
                          item.anchor_status,
                        )}`}
                      >
                        {anchorStatusLabel(item.anchor_status)}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-600 max-w-xs">
                      <div>
                        {item.anchor_attempts}{' '}
                        {item.anchor_attempts === 1 ? 'attempt' : 'attempts'}
                      </div>
                      {item.anchor_last_error && (
                        <div
                          data-testid="anchor-error"
                          className="mt-0.5 text-slate-500"
                        >
                          {explainAnchorError(item.anchor_last_error)}
                        </div>
                      )}
                      {item.anchor_next_attempt_at && (
                        <div className="mt-0.5 text-slate-400">
                          Next try after{' '}
                          {new Date(
                            item.anchor_next_attempt_at,
                          ).toLocaleTimeString()}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right">
                      {canRetryAnchor(item.anchor_status) ? (
                        <button
                          onClick={() => handleRetry(item.version_id)}
                          disabled={retryingId === item.version_id}
                          className="px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-xs"
                        >
                          {retryingId === item.version_id
                            ? 'Retrying...'
                            : 'Retry anchoring'}
                        </button>
                      ) : (
                        <span className="text-xs text-slate-400">
                          Waiting for the network
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
