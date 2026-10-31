'use client'

import Link from 'next/link'
import React, { useEffect, useState } from 'react'
import { AddStudentDialog } from '@/components/admin/add-student-dialog'
import { HealthBanner } from '@/components/admin/health-banner'
import {
  describeSyncResult,
  fetchAdminStats,
  triggerAdminSync,
  type AdminStats,
} from '@/lib/api/admin'

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // One request carries every number on the page (students, anchors, flags, last runs).
  const loadData = async () => {
    setLoading(true)
    try {
      setStats(await fetchAdminStats())
      setError(null)
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : 'Failed to load dashboard metrics',
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let ignore = false
    async function init() {
      try {
        const data = await fetchAdminStats()
        if (!ignore) {
          setStats(data)
          setError(null)
        }
      } catch (err: unknown) {
        if (!ignore) {
          setError(
            err instanceof Error
              ? err.message
              : 'Failed to load dashboard metrics',
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

  const totalStudents = stats?.total_students ?? null
  const adminManagedCount = stats?.admin_managed_students ?? 0
  const pendingAnchorsCount = stats?.pending_anchors ?? null
  const stuckAnchorsCount = stats?.failed_anchors ?? 0
  const openFlags = stats?.open_flags ?? null
  const syncRuns = stats?.recent_runs ?? []

  const handleTriggerSync = async () => {
    try {
      setSyncing(true)
      const res = await triggerAdminSync()
      await loadData()
      if (res.status !== 'completed') alert(describeSyncResult(res).text)
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  const lastSync = syncRuns[0]

  return (
    <div className="space-y-8">
      {/* Page Title & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            System Dashboard
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Overview of student digital passports, sync activity, and blockchain
            ledger status.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleTriggerSync}
            disabled={syncing}
            className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50 transition-colors shadow-sm"
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
            {syncing ? 'Running Sync...' : 'Trigger Sync'}
          </button>
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm"
          >
            + Add Student
          </button>
        </div>
      </div>

      <HealthBanner refreshKey={lastSync?.id ?? ''} />

      {error && (
        <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={loadData} className="underline font-semibold ml-4">
            Retry
          </button>
        </div>
      )}

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-5">
        <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Total Students
          </p>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-slate-900">
              {loading ? (
                <span
                  aria-hidden="true"
                  className="inline-block h-8 w-12 animate-pulse rounded bg-slate-200 align-middle"
                />
              ) : (
                (totalStudents ?? 0)
              )}
            </span>
            <span className="text-xs text-slate-500">issued passports</span>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span>Admin-managed: {adminManagedCount}</span>
            <Link
              href="/admin/students"
              className="text-indigo-600 font-medium hover:underline"
            >
              View all →
            </Link>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Pending Anchors
          </p>
          <div className="mt-2 flex items-baseline gap-2">
            <span
              className={`text-3xl font-extrabold ${
                (pendingAnchorsCount ?? 0) > 0
                  ? 'text-amber-600'
                  : 'text-slate-900'
              }`}
            >
              {loading ? (
                <span
                  aria-hidden="true"
                  className="inline-block h-8 w-12 animate-pulse rounded bg-slate-200 align-middle"
                />
              ) : (
                (pendingAnchorsCount ?? 0)
              )}
            </span>
            <span className="text-xs text-slate-500">unconfirmed</span>
          </div>
          {stuckAnchorsCount > 0 && (
            <p
              data-testid="stuck-anchors"
              className="mt-2 text-xs font-medium text-rose-600"
            >
              {stuckAnchorsCount} need{stuckAnchorsCount === 1 ? 's' : ''}{' '}
              attention
            </p>
          )}
          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span>Network: Polygon Amoy</span>
            <Link
              href="/admin/anchors"
              className="text-indigo-600 font-medium hover:underline"
            >
              Inspect →
            </Link>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Open Flags
          </p>
          <div className="mt-2 flex items-baseline gap-2">
            <span
              className={`text-3xl font-extrabold ${
                (openFlags ?? 0) > 0 ? 'text-rose-600' : 'text-slate-900'
              }`}
            >
              {loading ? (
                <span
                  aria-hidden="true"
                  className="inline-block h-8 w-12 animate-pulse rounded bg-slate-200 align-middle"
                />
              ) : (
                (openFlags ?? 0)
              )}
            </span>
            <span className="text-xs text-slate-500">from students</span>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span>Reports on passports</span>
            <Link
              href="/admin/flags"
              className="text-indigo-600 font-medium hover:underline"
            >
              Review →
            </Link>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Last Sheet Sync
          </p>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-xl font-bold capitalize text-slate-900">
              {loading ? 'N/A' : (lastSync?.status ?? 'No runs')}
            </span>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span>
              {lastSync?.started_at
                ? new Date(lastSync.started_at).toLocaleTimeString()
                : 'N/A'}
            </span>
            <Link
              href="/admin/sync"
              className="text-indigo-600 font-medium hover:underline"
            >
              History →
            </Link>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Sync Cadence
          </p>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-xl font-bold text-slate-900">
              Every 15 min
            </span>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span>Automated via GitHub</span>
            <span className="text-emerald-600 font-semibold">Active</span>
          </div>
        </div>
      </div>

      {/* Recent Sync Runs Preview */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
        <div className="p-6 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Recent Sync Operations
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Sync runs read the Google Sheet and issue versions automatically.
            </p>
          </div>
          <Link
            href="/admin/sync"
            className="text-xs font-medium text-indigo-600 hover:text-indigo-700 hover:underline"
          >
            View full log →
          </Link>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider border-b border-slate-100">
              <tr>
                <th className="px-6 py-3 font-semibold">Status</th>
                <th className="px-6 py-3 font-semibold">Started At</th>
                <th className="px-6 py-3 font-semibold">Rows Read</th>
                <th className="px-6 py-3 font-semibold">Versions Issued</th>
                <th className="px-6 py-3 font-semibold">Notes / Error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {syncRuns.length === 0 ? (
                <tr>
                  <td
                    colSpan={5}
                    className="px-6 py-8 text-center text-slate-500 text-xs"
                  >
                    No sync runs recorded yet.
                  </td>
                </tr>
              ) : (
                syncRuns.map((run) => (
                  <tr
                    key={run.id}
                    className="hover:bg-slate-50/50 transition-colors"
                  >
                    <td className="px-6 py-3.5">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium capitalize ${
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
                    <td className="px-6 py-3.5 text-xs font-mono text-slate-700">
                      {run.rows_read ?? 'N/A'}
                    </td>
                    <td className="px-6 py-3.5 text-xs font-mono font-medium text-slate-900">
                      {run.versions_created ?? 'N/A'}
                    </td>
                    <td className="px-6 py-3.5 text-xs text-slate-500 truncate max-w-xs">
                      {run.error ?? 'None'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      {showAdd && (
        <AddStudentDialog
          onClose={() => setShowAdd(false)}
          onDone={() => void loadData()}
        />
      )}
    </div>
  )
}
