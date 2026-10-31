'use client'

import Link from 'next/link'
import React, { useEffect, useState } from 'react'
import {
  FLAG_NOTE_MAX,
  fetchAdminFlags,
  updateAdminFlag,
  type AdminFlag,
  type AdminFlagStatus,
} from '@/lib/api/admin'
import { shareLinkFor } from '@/lib/share'

type Filter = AdminFlagStatus | 'all'

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'dismissed', label: 'Dismissed' },
  { value: 'all', label: 'All' },
]

const STATUS_STYLE: Record<AdminFlagStatus, string> = {
  open: 'bg-amber-50 text-amber-800 border-amber-200',
  resolved: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  dismissed: 'bg-slate-100 text-slate-600 border-slate-200',
}

function FlagCard({
  flag,
  onChanged,
}: {
  flag: AdminFlag
  onChanged: () => void
}) {
  const [note, setNote] = useState(flag.admin_note)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const noteId = `note-${flag.id}`

  async function act(status: 'resolved' | 'dismissed') {
    if (note.trim().length > FLAG_NOTE_MAX) {
      setError(`The note must be ${FLAG_NOTE_MAX} characters or fewer.`)
      return
    }
    setBusy(true)
    setError(null)
    try {
      await updateAdminFlag(flag.id, { status, admin_note: note.trim() })
      onChanged()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update the flag')
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm">
          <span className="font-semibold text-slate-900">
            {flag.student_email}
          </span>
          <span className="text-slate-500"> · </span>
          <Link
            href={`/admin/students/${encodeURIComponent(flag.passport_id)}`}
            className="font-mono text-xs text-indigo-600 hover:underline"
          >
            {flag.passport_id}
          </Link>
          <span className="text-slate-500"> · version {flag.version}</span>
        </div>
        <span
          className={`px-2.5 py-0.5 rounded-full border text-[11px] font-bold capitalize ${STATUS_STYLE[flag.status]}`}
        >
          {flag.status}
        </span>
      </div>

      <p className="text-sm text-slate-800 whitespace-pre-wrap break-words">
        {flag.comment}
      </p>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
        <span>Sent {new Date(flag.created_at).toLocaleString()}</span>
        {flag.resolved_at && (
          <span>
            Answered {new Date(flag.resolved_at).toLocaleString()}
            {flag.resolved_by ? ` by ${flag.resolved_by}` : ''}
          </span>
        )}
        <Link
          href={shareLinkFor('', flag.verification_code)}
          target="_blank"
          className="font-medium text-indigo-600 hover:underline"
        >
          Verify this version ↗
        </Link>
      </div>

      <div>
        <label
          htmlFor={noteId}
          className="block text-xs font-semibold text-slate-700 mb-1"
        >
          Reply to the student (optional)
        </label>
        <textarea
          id={noteId}
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          className="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
        />
        <p className="text-[11px] text-slate-500 mt-1">
          {note.trim().length} / {FLAG_NOTE_MAX}. The student sees this on their
          passport page.
        </p>
      </div>

      {error && (
        <p role="alert" className="text-xs text-rose-600">
          {error}
        </p>
      )}

      <div className="flex items-center justify-end gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => void act('dismissed')}
          className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-900 disabled:opacity-50"
        >
          Dismiss
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void act('resolved')}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-sm"
        >
          {flag.status === 'open' ? 'Resolve' : 'Update reply (resolved)'}
        </button>
      </div>
    </li>
  )
}

export default function AdminFlagsPage() {
  const [filter, setFilter] = useState<Filter>('open')
  const [flags, setFlags] = useState<AdminFlag[]>([])
  const [openCount, setOpenCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let ignore = false
    async function load() {
      try {
        const data = await fetchAdminFlags(
          filter === 'all' ? undefined : filter,
        )
        if (ignore) return
        setFlags(data.flags)
        setOpenCount(data.open_count)
        setError(null)
      } catch (err: unknown) {
        if (ignore) return
        setError(err instanceof Error ? err.message : 'Failed to load flags')
      } finally {
        if (!ignore) setLoading(false)
      }
    }
    void load()
    return () => {
      ignore = true
    }
  }, [filter, reload])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Student Flags
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Reports from students about a version of their passport. Resolving or
          dismissing a flag sends your reply to the student. Flags never change
          a passport.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2" role="tablist">
        {FILTERS.map((item) => (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={filter === item.value}
            onClick={() => {
              setLoading(true)
              setFilter(item.value)
            }}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
              filter === item.value
                ? 'bg-slate-900 text-white border-slate-900'
                : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
            }`}
          >
            {item.label}
            {item.value === 'open' ? ` (${openCount})` : ''}
          </button>
        ))}
      </div>

      {error && (
        <div
          role="alert"
          className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs"
        >
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-500">Loading flags...</p>
      ) : flags.length === 0 ? (
        <p className="text-sm text-slate-500">No flags here.</p>
      ) : (
        <ul className="space-y-4">
          {flags.map((flag) => (
            <FlagCard
              key={`${flag.id}-${flag.status}-${flag.admin_note}`}
              flag={flag}
              onChanged={() => setReload((value) => value + 1)}
            />
          ))}
        </ul>
      )}
    </div>
  )
}
