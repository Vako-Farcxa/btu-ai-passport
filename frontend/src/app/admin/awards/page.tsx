'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import React, { Suspense, useEffect, useState } from 'react'
import {
  SKILL_LEVELS,
  adminErrorMessage,
  awardAdminSkill,
  awardSyncNotice,
  fetchAdminSkills,
  parseAwardStudents,
  type AdminAwardResponse,
  type AdminCatalogSkill,
  type AwardRowResult,
  type SkillLevel,
} from '@/lib/api/admin'

const inputClass =
  'w-full px-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500'

const STATUS_STYLE: Record<AwardRowResult['status'], string> = {
  synced: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  pending: 'bg-amber-50 text-amber-700 border-amber-200',
  skipped: 'bg-slate-100 text-slate-600 border-slate-200',
  failed: 'bg-rose-50 text-rose-700 border-rose-200',
}

function asLevel(value: string): SkillLevel | '' {
  return SKILL_LEVELS.find((level) => level === value) ?? ''
}

function AwardForm() {
  const preselected = useSearchParams().get('skill') ?? ''
  const [skills, setSkills] = useState<AdminCatalogSkill[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [skillId, setSkillId] = useState(preselected)
  const [level, setLevel] = useState<SkillLevel | ''>('')
  const [awardedOn, setAwardedOn] = useState('')
  const [studentsText, setStudentsText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<AdminAwardResponse | null>(null)

  useEffect(() => {
    let ignore = false
    async function load() {
      try {
        const data = await fetchAdminSkills()
        if (!ignore) setSkills(data)
      } catch (err: unknown) {
        if (!ignore) {
          setLoadError(
            err instanceof Error ? err.message : 'Failed to load skills',
          )
        }
      }
    }
    void load()
    return () => {
      ignore = true
    }
  }, [])

  const selected = skills.find((skill) => skill.id === skillId)
  const effectiveLevel = level || asLevel(selected?.category ?? '')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setResult(null)
    const students = parseAwardStudents(studentsText)
    if (!skillId) {
      setError('Choose a skill.')
      return
    }
    if (students.length === 0) {
      setError('Enter at least one student email.')
      return
    }
    if (!effectiveLevel) {
      setError('This skill has no level yet. Choose one.')
      return
    }
    try {
      setSubmitting(true)
      setResult(
        await awardAdminSkill({
          skill_id: skillId,
          level: level || null,
          awarded_on: awardedOn || null,
          students,
        }),
      )
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to award skill')
    } finally {
      setSubmitting(false)
    }
  }

  const syncProblem = result ? awardSyncNotice(result) : null

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Award Skills
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Rows are added to the Google Sheet and the sync runs right away, so
          students appear in the database with their new passport version.
        </p>
        <p className="text-xs text-slate-500 mt-1">
          Adding a brand new student with their student ID, program and
          education level? Use{' '}
          <Link
            href="/admin/students"
            className="text-indigo-600 hover:underline"
          >
            Add student
          </Link>{' '}
          on the Students page. Students already in the Sheet keep their
          existing details.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5 space-y-4"
      >
        {(error || loadError) && (
          <div
            role="alert"
            className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs"
          >
            {error ?? loadError}
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-3">
          <div className="md:col-span-1">
            <label
              htmlFor="award-skill"
              className="block text-xs font-semibold text-slate-700 mb-1"
            >
              Skill
            </label>
            <select
              id="award-skill"
              value={skillId}
              onChange={(e) => setSkillId(e.target.value)}
              className={inputClass}
            >
              <option value="">Choose a skill...</option>
              {skills.map((skill) => (
                <option key={skill.id} value={skill.id}>
                  {skill.id} {skill.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="award-level"
              className="block text-xs font-semibold text-slate-700 mb-1"
            >
              Level
            </label>
            <select
              id="award-level"
              value={level}
              onChange={(e) => setLevel(asLevel(e.target.value))}
              className={inputClass}
            >
              <option value="">
                {selected?.category
                  ? `Skill default (${selected.category})`
                  : 'Skill default'}
              </option>
              {SKILL_LEVELS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="award-date"
              className="block text-xs font-semibold text-slate-700 mb-1"
            >
              Date earned
            </label>
            <input
              id="award-date"
              type="date"
              value={awardedOn}
              onChange={(e) => setAwardedOn(e.target.value)}
              className={inputClass}
            />
            <p className="text-[11px] text-slate-400 mt-1">
              Leave empty to use today&apos;s date
            </p>
          </div>
        </div>

        <div>
          <label
            htmlFor="award-students"
            className="block text-xs font-semibold text-slate-700 mb-1"
          >
            Student emails
          </label>
          <textarea
            id="award-students"
            rows={6}
            value={studentsText}
            onChange={(e) => setStudentsText(e.target.value)}
            placeholder={
              'one student per line\nnino.beridze@btu.edu.ge\nnew.student@btu.edu.ge, Tamar Chikovani'
            }
            className={`${inputClass} font-mono`}
          />
          <p className="text-[11px] text-slate-400 mt-1">
            Add a first and last name after the email only for students who do
            not have a passport yet.
          </p>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-sm"
          >
            {submitting ? 'Awarding and syncing...' : 'Award skill'}
          </button>
        </div>
      </form>

      {result && (
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
          <div className="p-4 border-b border-slate-100 space-y-1">
            <h2 className="text-base font-semibold text-slate-900">Result</h2>
            <p className="text-xs text-slate-500">
              Sync {result.sync_result.status}.{' '}
              {result.sync_result.versions_created} new passport version
              {result.sync_result.versions_created === 1 ? '' : 's'}.
            </p>
            {syncProblem && (
              <p className="text-xs text-amber-700">{syncProblem}</p>
            )}
          </div>
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider border-b border-slate-100">
              <tr>
                <th className="px-6 py-3 font-semibold">Email</th>
                <th className="px-6 py-3 font-semibold">Result</th>
                <th className="px-6 py-3 font-semibold">Passport</th>
                <th className="px-6 py-3 font-semibold">Version</th>
                <th className="px-6 py-3 font-semibold">Note</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {result.rows.map((row) => (
                <tr key={row.email}>
                  <td className="px-6 py-3 font-mono text-xs text-slate-700">
                    {row.email}
                  </td>
                  <td className="px-6 py-3 text-xs">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border ${STATUS_STYLE[row.status]}`}
                    >
                      {row.status}
                    </span>
                  </td>
                  <td className="px-6 py-3 font-mono text-xs text-slate-600">
                    {row.passport_id || '-'}
                  </td>
                  <td className="px-6 py-3 font-mono text-xs text-slate-600">
                    {row.version || '-'}
                  </td>
                  <td className="px-6 py-3 text-xs text-slate-500">
                    {row.error
                      ? `${adminErrorMessage(row.error)} (${row.error})`
                      : row.status === 'pending'
                        ? 'Saved in the Sheet. Will sync shortly.'
                        : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function AdminAwardsPage() {
  return (
    <Suspense
      fallback={<p className="text-xs text-slate-400">Loading skills...</p>}
    >
      <AwardForm />
    </Suspense>
  )
}
