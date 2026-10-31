'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import React, { Suspense, useEffect, useState } from 'react'
import {
  fetchAdminStudent,
  restoreAdminStudent,
  retryAdminAnchor,
  revokeAdminVersion,
  unrevokeAdminVersion,
  type AdminStudentDetail,
} from '@/lib/api/admin'
import {
  anchorBadgeClasses,
  anchorStatusLabel,
  canRetryAnchor,
  explainAnchorError,
  retryMessage,
} from '@/lib/anchor-status'
import { explorerTxUrlFor } from '@/lib/explorer'
import { shareLinkFor } from '@/lib/share'

function StudentDetailContent() {
  const params = useParams()
  const rawId = params?.passport_id
  const passportId: string = (Array.isArray(rawId) ? rawId[0] : rawId) || ''

  const [student, setStudent] = useState<AdminStudentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [anchorNotice, setAnchorNotice] = useState<ReturnType<
    typeof retryMessage
  > | null>(null)
  const [busy, setBusy] = useState(false)
  const [reloads, setReloads] = useState(0)

  async function act(question: string, run: () => Promise<void>) {
    if (busy || !confirm(question)) return
    setBusy(true)
    setActionError(null)
    try {
      await run()
      setReloads((count) => count + 1)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  async function retryAnchoring(versionId: string) {
    if (busy) return
    setBusy(true)
    setActionError(null)
    setAnchorNotice(null)
    try {
      setAnchorNotice(retryMessage(await retryAdminAnchor(versionId)))
      setReloads((count) => count + 1)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Retry failed')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (!passportId) return
    let ignore = false
    async function init() {
      try {
        const data = await fetchAdminStudent(passportId)
        if (!ignore) {
          setStudent(data)
          setError(null)
        }
      } catch (err: unknown) {
        if (!ignore) {
          setError(
            err instanceof Error
              ? err.message
              : 'Failed to load student details',
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
  }, [passportId, reloads])

  if (loading) {
    return (
      <div className="py-24 text-center text-slate-500 text-sm">
        Loading student passport details...
      </div>
    )
  }

  if (error || !student) {
    return (
      <div className="space-y-4">
        <Link
          href="/admin/students"
          className="text-xs text-indigo-600 font-medium hover:underline"
        >
          ← Back to Students
        </Link>
        <div className="p-6 bg-rose-50 border border-rose-200 rounded-2xl text-rose-800 text-sm">
          {error || 'Student not found'}
        </div>
      </div>
    )
  }

  const latestVersion = student.versions[0]

  return (
    <div className="space-y-8">
      {/* Back button & Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Link
          href="/admin/students"
          className="hover:text-slate-900 transition-colors"
        >
          Students
        </Link>
        <span>/</span>
        <span className="font-mono text-slate-700">{student.passport_id}</span>
      </div>

      {/* Header Profile Card */}
      <div className="bg-white p-6 md:p-8 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">
              {student.full_name}
            </h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
              {student.admin_managed ? 'Legacy admin record' : 'Google Sheet'}
            </span>
            {student.deleted_at && (
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
                Archived
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500">
            <span>
              Email:{' '}
              <strong className="font-mono text-slate-700">
                {student.email}
              </strong>
            </span>
            <span>•</span>
            <span>
              Permanent Passport ID:{' '}
              <strong className="font-mono text-slate-900 px-2 py-0.5 bg-slate-100 rounded border border-slate-200">
                {student.passport_id}
              </strong>
            </span>
            <span>•</span>
            <span>Versions Issued: {student.versions.length}</span>
          </div>
        </div>

        {/* Public Verify Link for latest version */}
        {latestVersion && (
          <div className="flex items-center gap-3">
            <Link
              href={shareLinkFor('', latestVersion.verification_code)}
              target="_blank"
              className="inline-flex items-center gap-2 px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-xs font-semibold transition-colors"
            >
              Verify Code:{' '}
              <span className="font-mono text-indigo-600">
                {latestVersion.verification_code}
              </span>
              <svg
                className="w-3.5 h-3.5 text-slate-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                />
              </svg>
            </Link>
          </div>
        )}
      </div>

      {student.deleted_at && (
        <div
          role="status"
          data-testid="archived-banner"
          className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-900 text-xs flex items-center justify-between gap-3"
        >
          <div>
            <strong>This student is archived.</strong> Since{' '}
            {new Date(student.deleted_at).toLocaleDateString()} every code below
            verifies as Revoked, they cannot open their passport or download
            PDFs, and the sync will not add new versions.
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void act(
                `Restore ${student.full_name}? Their codes will verify as valid again and they can open their passport.`,
                () => restoreAdminStudent(student.passport_id),
              )
            }
            className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg text-xs font-semibold transition-colors shrink-0"
          >
            Restore student
          </button>
        </div>
      )}
      {anchorNotice && (
        <div
          role="status"
          data-testid="anchor-notice"
          className={`p-4 rounded-xl border text-xs ${
            anchorNotice.kind === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : anchorNotice.kind === 'warning'
                ? 'bg-amber-50 border-amber-200 text-amber-800'
                : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          {anchorNotice.text}
        </div>
      )}

      {actionError && (
        <div
          role="alert"
          className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs"
        >
          {actionError}
        </div>
      )}

      {/* Where skills come from */}
      <div className="p-4 rounded-xl bg-blue-50/80 border border-blue-200/80 text-blue-900 text-xs flex items-center justify-between gap-3">
        <div>
          <strong>Skills come from the Google Sheet.</strong> To give this
          student a skill, award it from the Award Skills page. It is written to
          the Sheet first, then synced into this ledger.
        </div>
        <Link
          href="/admin/awards"
          className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition-colors shrink-0"
        >
          Award a skill
        </Link>
      </div>

      {/* Version Records Breakdown */}
      <div className="space-y-6">
        <h2 className="text-lg font-bold text-slate-900">
          Passport Version Ledger
        </h2>

        {student.versions.length === 0 ? (
          <div className="p-8 bg-white rounded-2xl border border-slate-200 text-center text-slate-500 text-xs">
            No versions issued for this student yet. Award a skill to create
            Version 1.
          </div>
        ) : (
          student.versions.map((ver, idx) => (
            <div
              key={ver.id}
              className={`bg-white rounded-2xl border ${
                idx === 0
                  ? 'border-indigo-200/80 shadow-xs'
                  : 'border-slate-200'
              } overflow-hidden`}
            >
              {/* Version Header */}
              <div className="p-5 bg-slate-50/60 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="font-extrabold text-base text-slate-900">
                    Version {ver.version_number}
                  </span>
                  {idx === 0 && (
                    <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
                      CURRENT LATEST
                    </span>
                  )}
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${anchorBadgeClasses(
                      ver.anchor_status,
                    )}`}
                  >
                    Anchor: {anchorStatusLabel(ver.anchor_status)}
                  </span>
                  {ver.revoked_at && (
                    <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
                      REVOKED {new Date(ver.revoked_at).toLocaleDateString()}
                    </span>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500 font-mono">
                  <span>
                    Issued: {new Date(ver.issued_at).toLocaleDateString()}
                  </span>
                  <span>•</span>
                  <span>Code: {ver.verification_code}</span>
                  <Link
                    href={shareLinkFor('', ver.verification_code)}
                    target="_blank"
                    className="text-indigo-600 hover:underline"
                  >
                    Verify ↗
                  </Link>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void act(
                        ver.revoked_at
                          ? `Restore version ${ver.version_number}? Its code will verify normally again.`
                          : `Revoke version ${ver.version_number}? Its code will show Revoked and its PDF will be refused. You can restore it later.`,
                        () =>
                          ver.revoked_at
                            ? unrevokeAdminVersion(ver.id)
                            : revokeAdminVersion(ver.id),
                      )
                    }
                    className={`font-sans font-semibold hover:underline disabled:opacity-60 ${
                      ver.revoked_at ? 'text-emerald-700' : 'text-rose-600'
                    }`}
                  >
                    {ver.revoked_at ? 'Restore version' : 'Revoke version'}
                  </button>
                  {ver.tx_hash && explorerTxUrlFor(ver.tx_hash) && (
                    <>
                      <span>•</span>
                      <a
                        href={explorerTxUrlFor(ver.tx_hash) ?? undefined}
                        target="_blank"
                        rel="noreferrer"
                        className="text-indigo-600 hover:underline"
                      >
                        PolygonScan ↗
                      </a>
                    </>
                  )}
                </div>
              </div>

              {ver.anchor_status !== 'confirmed' && (
                <div
                  data-testid="anchor-detail"
                  className="px-5 py-3 border-b border-slate-100 bg-amber-50/40 text-xs text-slate-700 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div>
                    <strong>
                      {ver.anchor_status === 'failed_permanent'
                        ? 'Anchoring needs attention.'
                        : 'Waiting for the blockchain.'}
                    </strong>{' '}
                    Attempts so far: {ver.anchor_attempts}.
                    {ver.anchor_last_error
                      ? ` ${explainAnchorError(ver.anchor_last_error)}`
                      : ''}
                  </div>
                  {canRetryAnchor(ver.anchor_status) && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void retryAnchoring(ver.id)}
                      className="px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-xs self-start"
                    >
                      Retry anchoring
                    </button>
                  )}
                </div>
              )}

              {/* Skills Table in Version */}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50/40 text-slate-500 uppercase tracking-wider border-b border-slate-100">
                    <tr>
                      <th className="px-6 py-2.5 font-semibold">#</th>
                      <th className="px-6 py-2.5 font-semibold">Skill Title</th>
                      <th className="px-6 py-2.5 font-semibold">
                        Badge / Stamp
                      </th>
                      <th className="px-6 py-2.5 font-semibold">
                        Date Awarded
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {ver.skills.length === 0 ? (
                      <tr>
                        <td
                          colSpan={4}
                          className="px-6 py-6 text-center text-slate-500"
                        >
                          No skills recorded on this version.
                        </td>
                      </tr>
                    ) : (
                      ver.skills.map((skill, sIdx) => (
                        <tr
                          key={skill.id || sIdx}
                          className="hover:bg-slate-50/50"
                        >
                          <td className="px-6 py-3 font-mono text-slate-500">
                            {skill.position}
                          </td>
                          <td className="px-6 py-3 font-medium text-slate-900">
                            {skill.skill}
                          </td>
                          <td className="px-6 py-3 font-mono text-slate-600">
                            {skill.badge ? (
                              <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                                {skill.badge}
                              </span>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td className="px-6 py-3 text-slate-600">
                            {skill.awarded_on || 'Unavailable'}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default function AdminStudentDetailPage() {
  return (
    <Suspense
      fallback={
        <div className="py-24 text-center text-slate-500 text-sm">
          Loading student passport details...
        </div>
      }
    >
      <StudentDetailContent />
    </Suspense>
  )
}
