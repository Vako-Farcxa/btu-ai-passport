'use client'

import React, { useCallback, useEffect, useState } from 'react'
import {
  auditActionLabel,
  fetchAdminAudit,
  type AdminAuditEntry,
} from '@/lib/api/admin'

function detailText(detail: AdminAuditEntry['detail']): string {
  return Object.entries(detail)
    .map(([key, value]) => `${key.replace(/_/g, ' ')}: ${String(value)}`)
    .join(', ')
}

export default function AdminAuditPage() {
  const [entries, setEntries] = useState<AdminAuditEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setEntries(await fetchAdminAudit(100))
      setError(null)
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : 'Failed to load the activity log',
      )
    }
  }, [])

  useEffect(() => {
    // Load once on mount, the same way the other admin pages do.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Activity
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Who changed what in this panel, newest first. Sheet edits made
            outside the panel are not listed here.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="text-xs font-medium text-indigo-600 hover:text-indigo-800 self-start sm:self-auto"
        >
          Refresh
        </button>
      </div>

      {error && (
        <p
          role="alert"
          className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs"
        >
          {error}
        </p>
      )}

      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Recent admin activity</caption>
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider border-b border-slate-100">
            <tr>
              <th scope="col" className="px-6 py-3 font-semibold">
                When
              </th>
              <th scope="col" className="px-6 py-3 font-semibold">
                Admin
              </th>
              <th scope="col" className="px-6 py-3 font-semibold">
                Action
              </th>
              <th scope="col" className="px-6 py-3 font-semibold">
                Target
              </th>
              <th scope="col" className="px-6 py-3 font-semibold">
                Details
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {entries === null && !error ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-6 py-12 text-center text-slate-400 text-xs"
                >
                  Loading activity...
                </td>
              </tr>
            ) : entries !== null && entries.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-6 py-12 text-center text-slate-400 text-xs"
                >
                  Nothing has been changed in the panel yet.
                </td>
              </tr>
            ) : (
              (entries ?? []).map((entry) => (
                <tr key={entry.id}>
                  <td className="px-6 py-3.5 text-xs text-slate-600 whitespace-nowrap">
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                  <td className="px-6 py-3.5 text-xs text-slate-800">
                    {entry.actor}
                  </td>
                  <td className="px-6 py-3.5 text-xs font-medium text-slate-900">
                    {auditActionLabel(entry.action)}
                  </td>
                  <td className="px-6 py-3.5 text-xs font-mono text-slate-700 break-all">
                    {entry.target}
                  </td>
                  <td className="px-6 py-3.5 text-xs text-slate-500">
                    {detailText(entry.detail)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
