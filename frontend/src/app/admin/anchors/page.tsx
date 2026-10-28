'use client'

import Link from 'next/link'
import React, { useEffect, useState } from 'react'
import {
  fetchAdminPendingVersions,
  retryAdminAnchor,
  type AdminVersionPending,
} from '@/lib/api/admin'

export default function AdminAnchorsPage() {
  const [pending, setPending] = useState<AdminVersionPending[]>([])
  const [loading, setLoading] = useState(true)
  const [retryingId, setRetryingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const loadPending = async () => {
    try {
      setLoading(true)
      const data = await fetchAdminPendingVersions()
      setPending(data.versions)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load pending versions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadPending()
  }, [])

  const handleRetry = async (versionId: string) => {
    try {
      setRetryingId(versionId)
      setMessage(null)
      setError(null)
      const res = await retryAdminAnchor(versionId)
      setMessage(`Anchor transaction status: ${res.status}`)
      await loadPending()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Anchor retry failed')
    } finally {
      setRetryingId(null)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Blockchain Anchor Monitor</h1>
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

      {message && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center justify-between">
          <span>{message}</span>
          <button onClick={() => setMessage(null)} className="text-emerald-600 font-bold ml-4">
            ✕
          </button>
        </div>
      )}

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-rose-600 font-bold ml-4">
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
          <p className="mt-1 text-sm font-bold text-slate-900">Polygon Amoy Testnet</p>
          <p className="text-xs text-slate-400 mt-1">Chain ID: 80002</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Privacy Guarantee
          </span>
          <p className="mt-1 text-sm font-bold text-slate-900">Zero PII On-Chain</p>
          <p className="text-xs text-slate-400 mt-1">Only content_hash & verification_id_hash</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Pending Queue Size
          </span>
          <p className="mt-1 text-sm font-bold text-slate-900">{pending.length} versions</p>
          <p className="text-xs text-slate-400 mt-1">Awaiting confirmation or retry</p>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
        <div className="p-6 border-b border-slate-100">
          <h2 className="text-base font-semibold text-slate-900">Pending & Failed Anchors</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Versions whose blockchain transaction has not yet been confirmed on Polygon Amoy.
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
                <th className="px-6 py-3 font-semibold text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-slate-400 text-xs">
                    Checking queue...
                  </td>
                </tr>
              ) : pending.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-slate-400 text-xs">
                    All issued passport versions are fully confirmed on the blockchain! 🎉
                  </td>
                </tr>
              ) : (
                pending.map((item) => (
                  <tr key={item.version_id} className="hover:bg-slate-50/50 transition-colors">
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
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${
                          item.anchor_status === 'pending'
                            ? 'bg-amber-50 text-amber-700 border border-amber-200'
                            : 'bg-rose-50 text-rose-700 border border-rose-200'
                        }`}
                      >
                        {item.anchor_status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => handleRetry(item.version_id)}
                        disabled={retryingId === item.version_id}
                        className="px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-xs"
                      >
                        {retryingId === item.version_id ? 'Retrying...' : 'Retry Anchor'}
                      </button>
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
