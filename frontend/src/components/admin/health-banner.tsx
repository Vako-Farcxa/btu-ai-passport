'use client'

import Link from 'next/link'
import React, { useCallback, useEffect, useState } from 'react'

import { alertLink, alertReason } from '@/lib/admin-health'
import { fetchAdminHealth, type AdminHealth } from '@/lib/api/admin'

type State =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; health: AdminHealth }

/**
 * Red or amber banner at the top of the admin dashboard when something needs a person: the
 * last sync failed, no sync for hours, an anchor gave up or has been waiting too long,
 * or the database consistency check found problems. Nothing is shown while all is well.
 * `refreshKey` reloads it, for example after a manual sync.
 */
export function HealthBanner({ refreshKey = '' }: { refreshKey?: string }) {
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [tick, setTick] = useState(0)

  const recheck = useCallback(() => setTick((value) => value + 1), [])

  useEffect(() => {
    let ignore = false
    async function load() {
      try {
        const health = await fetchAdminHealth()
        if (!ignore) setState({ kind: 'ready', health })
      } catch (err: unknown) {
        if (!ignore) {
          setState({
            kind: 'error',
            message:
              err instanceof Error
                ? err.message
                : 'Failed to load system health',
          })
        }
      }
    }
    void load()
    return () => {
      ignore = true
    }
  }, [refreshKey, tick])

  if (state.kind === 'loading') return null

  if (state.kind === 'error') {
    return (
      <div
        data-testid="health-banner"
        data-severity="warning"
        role="status"
        className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-sm flex items-center justify-between"
      >
        <span>System health could not be checked. {state.message}</span>
        <button onClick={recheck} className="underline font-semibold ml-4">
          Retry
        </button>
      </div>
    )
  }

  const { health } = state
  if (health.alerts.length === 0) return null

  const critical = health.status === 'critical'
  return (
    <div
      data-testid="health-banner"
      data-severity={critical ? 'critical' : 'warning'}
      role={critical ? 'alert' : 'status'}
      className={`p-4 rounded-xl border text-sm ${
        critical
          ? 'bg-rose-50 border-rose-200 text-rose-900'
          : 'bg-amber-50 border-amber-200 text-amber-900'
      }`}
    >
      <div className="flex items-center justify-between">
        <p className="font-semibold">
          {critical ? 'Needs attention now' : 'Worth a look'}
        </p>
        <button onClick={recheck} className="underline font-semibold ml-4">
          Check again
        </button>
      </div>
      <ul className="mt-2 space-y-2">
        {health.alerts.map((alert) => {
          const reason = alertReason(alert)
          const link = alertLink(alert)
          return (
            <li
              key={alert.code}
              data-testid={`health-alert-${alert.code}`}
              data-severity={alert.severity}
            >
              <span
                className={`inline-block w-2 h-2 rounded-full mr-2 ${
                  alert.severity === 'critical' ? 'bg-rose-600' : 'bg-amber-500'
                }`}
                aria-hidden="true"
              />
              <span className="font-medium">{alert.message}</span>
              {reason && (
                <span data-testid="health-alert-reason" className="block ml-4">
                  Reason: {reason}
                </span>
              )}
              {link && (
                <Link
                  href={link.href}
                  className="block ml-4 underline font-medium"
                >
                  {link.label}
                </Link>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
