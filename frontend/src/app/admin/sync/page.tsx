'use client'

import React, { useEffect, useState } from 'react'
import {
  fetchAdminSyncRuns,
  triggerAdminSync,
  type AdminSyncRun,
} from '@/lib/api/admin'

export default function AdminSyncPage() {
  const [runs, setRuns] = useState<AdminSyncRun[]>([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const loadRuns = async () => {
    setLoading(true)
    try {
      const data = await fetchAdminSyncRuns(50)
      setRuns(data.runs)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load sync runs')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let ignore = false
    async function init() {
      try {
        const data = await fetchAdminSyncRuns(50)
        if (!ignore) {
          setRuns(data.runs)
          setError(null)
        }
      } catch (err: unknown) {
        if (!ignore) {
          setError(
            err instanceof Error ? err.message : 'Failed to load sync runs',
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

  const handleTriggerSync = async () => {
    try {
      setSyncing(true)
      setSuccessMsg(null)
      setError(null)
      const res = await triggerAdminSync()
      setSuccessMsg(
        `Sync completed successfully! Rows read: ${res.rows_read}, New versions created: ${res.versions_created}`,
      )
      await loadRuns()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Sync execution failed')
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Google Sheet Sync Monitor
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Periodically reads BTU&apos;s student database, computes
            cryptographic hashes, and creates new versions.
          </p>
        </div>
        <button
          onClick={handleTriggerSync}
          disabled={syncing}
          className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50 transition-colors shadow-sm self-start sm:self-auto"
        >
          <svg
            className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          {syncing ? 'Processing Sync...' : 'Trigger Sync Now'}
        </button>
      </div>

      {successMsg && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center justify-between">
          <span>{successMsg}</span>
          <button
            onClick={() => setSuccessMsg(null)}
            className="text-emerald-600 font-bold ml-4"
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

      {/* Info Card */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Sync Schedule
          </span>
          <p className="mt-1 text-sm font-bold text-slate-900">
            Every 15 minutes
          </p>
          <p className="text-xs text-slate-400 mt-1">
            Configured in .github/workflows/sync.yml
          </p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Deduplication Guarantee
          </span>
          <p className="mt-1 text-sm font-bold text-slate-900">
            Zero duplicate versions
          </p>
          <p className="text-xs text-slate-400 mt-1">
            keccak256 skill fingerprint verification
          </p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Admin Students Isolation
          </span>
          <p className="mt-1 text-sm font-bold text-slate-900">Protected</p>
          <p className="text-xs text-slate-400 mt-1">
            Admin-managed students are never overwritten
          </p>
        </div>
      </div>

      {/* Sync Runs History Table */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
        <div className="p-6 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Sync Execution History
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Logs of past automated and manual sync executions.
            </p>
          </div>
          <button
            onClick={loadRuns}
            className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
          >
            Refresh Logs
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider border-b border-slate-100">
              <tr>
                <th className="px-6 py-3 font-semibold">Status</th>
                <th className="px-6 py-3 font-semibold">Started At</th>
                <th className="px-6 py-3 font-semibold">Finished At</th>
                <th className="px-6 py-3 font-semibold">Rows Processed</th>
                <th className="px-6 py-3 font-semibold">Versions Created</th>
                <th className="px-6 py-3 font-semibold">
                  Error Message / Notes
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-6 py-12 text-center text-slate-400 text-xs"
                  >
                    Loading sync history...
                  </td>
                </tr>
              ) : runs.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-6 py-12 text-center text-slate-400 text-xs"
                  >
                    No sync executions logged yet.
                  </td>
                </tr>
              ) : (
                runs.map((run) => (
                  <tr
                    key={run.id}
                    className="hover:bg-slate-50/50 transition-colors"
                  >
                    <td className="px-6 py-3.5">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${
                          run.status === 'completed'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : run.status === 'running'
                              ? 'bg-sky-50 text-sky-700 border border-sky-200'
                              : run.status === 'skipped'
                                ? 'bg-slate-100 text-slate-600'
                                : 'bg-rose-50 text-rose-700 border border-rose-200'
                        }`}
                      >
                        {run.status}
                      </span>
                    </td>
                    <td className="px-6 py-3.5 text-xs text-slate-600">
                      {new Date(run.started_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-3.5 text-xs text-slate-600">
                      {run.finished_at
                        ? new Date(run.finished_at).toLocaleString()
                        : 'In Progress'}
                    </td>
                    <td className="px-6 py-3.5 text-xs font-mono font-medium text-slate-800">
                      {run.rows_read ?? '—'}
                    </td>
                    <td className="px-6 py-3.5 text-xs font-mono font-semibold text-slate-900">
                      {run.versions_created ?? '—'}
                    </td>
                    <td className="px-6 py-3.5 text-xs text-slate-500 truncate max-w-sm">
                      {run.error ?? 'None (Successful)'}
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
