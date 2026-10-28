'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import React, { Suspense, useEffect, useState } from 'react'
import {
  fetchAdminStudent,
  addAdminSkill,
  removeAdminSkill,
  type AdminStudentDetail,
} from '@/lib/api/admin'

function StudentDetailContent() {
  const params = useParams()
  const rawId = params?.passport_id
  const passportId: string = (Array.isArray(rawId) ? rawId[0] : rawId) || ''

  const [student, setStudent] = useState<AdminStudentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Add skill form state
  const [skillName, setSkillName] = useState('')
  const [badgeCode, setBadgeCode] = useState('BDG-AI-001')
  const [awardedOn, setAwardedOn] = useState(new Date().toISOString().slice(0, 10))
  const [submittingSkill, setSubmittingSkill] = useState(false)
  const [skillError, setSkillError] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)

  const loadStudent = async () => {
    if (!passportId) return
    try {
      setLoading(true)
      const data = await fetchAdminStudent(passportId)
      setStudent(data)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load student details')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadStudent()
  }, [passportId])

  const handleAddSkill = async (e: React.FormEvent) => {
    e.preventDefault()
    setSkillError(null)

    if (!passportId) return
    if (!skillName.trim()) {
      setSkillError('Skill name is required')
      return
    }

    try {
      setSubmittingSkill(true)
      const updated = await addAdminSkill(passportId, {
        skill: skillName.trim(),
        badge: badgeCode.trim(),
        awarded_on: awardedOn || null,
      })
      setStudent(updated)
      setSkillName('')
      setShowAddForm(false)
    } catch (err: unknown) {
      setSkillError(err instanceof Error ? err.message : 'Failed to add skill')
    } finally {
      setSubmittingSkill(false)
    }
  }

  const handleRemoveSkill = async (skillId: string, name: string) => {
    if (!passportId) return
    if (!confirm(`Remove skill "${name}"? This will automatically issue a new passport version.`)) {
      return
    }
    try {
      const updated = await removeAdminSkill(passportId, skillId)
      setStudent(updated)
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to remove skill')
    }
  }

  if (loading) {
    return (
      <div className="py-24 text-center text-slate-400 text-sm">
        Loading student passport details...
      </div>
    )
  }

  if (error || !student) {
    return (
      <div className="space-y-4">
        <Link href="/admin/students" className="text-xs text-indigo-600 font-medium hover:underline">
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
        <Link href="/admin/students" className="hover:text-slate-900 transition-colors">
          Students
        </Link>
        <span>/</span>
        <span className="font-mono text-slate-700">{student.passport_id}</span>
      </div>

      {/* Header Profile Card */}
      <div className="bg-white p-6 md:p-8 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">{student.full_name}</h1>
            {student.admin_managed ? (
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200">
                Admin Managed
              </span>
            ) : (
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                Google Sheet Managed
              </span>
            )}
            {student.deleted_at && (
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
                Archived
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500">
            <span>
              Email: <strong className="font-mono text-slate-700">{student.email}</strong>
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
              href={`/verify`}
              target="_blank"
              className="inline-flex items-center gap-2 px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-xs font-semibold transition-colors"
            >
              Verify Code: <span className="font-mono text-indigo-600">{latestVersion.verification_code}</span>
              <svg className="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </Link>
          </div>
        )}
      </div>

      {/* Sheet vs Admin Managed Info Banner */}
      {!student.admin_managed ? (
        <div className="p-4 rounded-xl bg-blue-50/80 border border-blue-200/80 text-blue-900 text-xs flex items-center gap-3">
          <svg className="w-5 h-5 text-blue-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <strong>Google Sheet Managed Student:</strong> Skills and name changes for this student originate from BTU&apos;s Google Sheet.
            To add, remove, or modify skills, edit the sheet and trigger a sync.
          </div>
        </div>
      ) : (
        <div className="p-4 rounded-xl bg-purple-50/80 border border-purple-200/80 text-purple-900 text-xs flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <svg className="w-5 h-5 text-purple-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            <div>
              <strong>Admin Managed Student:</strong> You have full control over skills.
              Adding or removing a skill will automatically issue a new passport version, generate multi-page PDFs, and anchor to Polygon Amoy.
            </div>
          </div>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="px-3 py-1.5 bg-purple-700 hover:bg-purple-800 text-white rounded-lg text-xs font-semibold transition-colors shrink-0"
          >
            {showAddForm ? 'Cancel' : '+ Add Skill'}
          </button>
        </div>
      )}

      {/* Add Skill Form (Inline Collapsible) */}
      {showAddForm && student.admin_managed && (
        <div className="bg-white p-6 rounded-2xl border border-purple-200 shadow-sm space-y-4 animate-in fade-in duration-150">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-900">Add Skill to Student</h2>
            <span className="text-xs text-purple-600 font-semibold">
              Will create Version {latestVersion ? latestVersion.version_number + 1 : 1}
            </span>
          </div>

          {skillError && (
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs">
              {skillError}
            </div>
          )}

          <form onSubmit={handleAddSkill} className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Skill Name *
              </label>
              <input
                type="text"
                required
                placeholder="e.g. AI Prompt Engineering"
                value={skillName}
                onChange={(e) => setSkillName(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Badge / Stamp Code
              </label>
              <select
                value={badgeCode}
                onChange={(e) => setBadgeCode(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500"
              >
                <option value="BDG-AI-001">BDG-AI-001 (AI Skill)</option>
                <option value="BDG-AI-002">BDG-AI-002 (AI Applied Skill)</option>
                <option value="BDG-AI-003">BDG-AI-003 (AI Advanced Skill)</option>
                <option value="Foundation">Foundation Badge</option>
                <option value="Stamp">Stamp Badge</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Awarded On Date
              </label>
              <input
                type="date"
                value={awardedOn}
                onChange={(e) => setAwardedOn(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500"
              />
            </div>

            <div className="md:col-span-3 flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-900"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submittingSkill}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50"
              >
                {submittingSkill ? 'Issuing Version...' : 'Confirm & Issue New Version'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Version Records Breakdown */}
      <div className="space-y-6">
        <h2 className="text-lg font-bold text-slate-900">Passport Version Ledger</h2>

        {student.versions.length === 0 ? (
          <div className="p-8 bg-white rounded-2xl border border-slate-200 text-center text-slate-400 text-xs">
            No versions issued for this student yet. Add a skill to create Version 1.
          </div>
        ) : (
          student.versions.map((ver, idx) => (
            <div
              key={ver.id}
              className={`bg-white rounded-2xl border ${
                idx === 0 ? 'border-indigo-200/80 shadow-xs' : 'border-slate-200'
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
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium capitalize ${
                      ver.anchor_status === 'confirmed'
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : ver.anchor_status === 'pending'
                        ? 'bg-amber-50 text-amber-700 border border-amber-200'
                        : 'bg-rose-50 text-rose-700 border border-rose-200'
                    }`}
                  >
                    Anchor: {ver.anchor_status}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500 font-mono">
                  <span>Issued: {new Date(ver.issued_at).toLocaleDateString()}</span>
                  <span>•</span>
                  <span>Code: {ver.verification_code}</span>
                  {ver.tx_hash && (
                    <>
                      <span>•</span>
                      <a
                        href={`https://amoy.polygonscan.com/tx/${ver.tx_hash}`}
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

              {/* Skills Table in Version */}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50/40 text-slate-500 uppercase tracking-wider border-b border-slate-100">
                    <tr>
                      <th className="px-6 py-2.5 font-semibold">#</th>
                      <th className="px-6 py-2.5 font-semibold">Skill Title</th>
                      <th className="px-6 py-2.5 font-semibold">Badge / Stamp</th>
                      <th className="px-6 py-2.5 font-semibold">Date Awarded</th>
                      {student.admin_managed && idx === 0 && (
                        <th className="px-6 py-2.5 font-semibold text-right">Actions</th>
                      )}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {ver.skills.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="px-6 py-6 text-center text-slate-400">
                          No skills recorded on this version.
                        </td>
                      </tr>
                    ) : (
                      ver.skills.map((skill, sIdx) => (
                        <tr key={skill.id || sIdx} className="hover:bg-slate-50/50">
                          <td className="px-6 py-3 font-mono text-slate-400">{skill.position}</td>
                          <td className="px-6 py-3 font-medium text-slate-900">{skill.skill}</td>
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
                          {student.admin_managed && idx === 0 && (
                            <td className="px-6 py-3 text-right">
                              <button
                                onClick={() => handleRemoveSkill(skill.id, skill.skill)}
                                className="text-rose-600 hover:text-rose-800 font-semibold transition-colors"
                              >
                                Remove
                              </button>
                            </td>
                          )}
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
        <div className="py-24 text-center text-slate-400 text-sm">
          Loading student passport details...
        </div>
      }
    >
      <StudentDetailContent />
    </Suspense>
  )
}

