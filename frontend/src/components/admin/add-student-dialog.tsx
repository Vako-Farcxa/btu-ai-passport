'use client'

import Link from 'next/link'
import React, { useEffect, useState } from 'react'

import { EDUCATION_LEVELS, programsForLevel } from '@/lib/btu-programs'
import { cleanEmail, cleanName, emailError, nameError } from '@/lib/validation'
import {
  SKILL_LEVELS,
  adminErrorMessage,
  awardAdminSkill,
  awardSyncNotice,
  fetchAdminSkills,
  type AdminAwardResponse,
  type AdminCatalogSkill,
  type SkillLevel,
} from '@/lib/api/admin'

const inputClass =
  'w-full px-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500'

type Field = 'firstName' | 'lastName' | 'email' | 'skill'

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null
  return (
    <p id={id} role="alert" className="text-[11px] text-rose-600 mt-1">
      {message}
    </p>
  )
}

function asLevel(value: string): SkillLevel | '' {
  return SKILL_LEVELS.find((level) => level === value) ?? ''
}

/**
 * Adds a student the same way awards work: one new row in the Google Sheet, then the
 * sync. A Sheet row is one skill award, so a skill is required. Nothing is written to
 * the database directly.
 */
export function AddStudentDialog({
  onClose,
  onDone,
}: {
  onClose: () => void
  onDone?: () => void
}) {
  const [skills, setSkills] = useState<AdminCatalogSkill[]>([])
  const [skillsError, setSkillsError] = useState<string | null>(null)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [program, setProgram] = useState('')
  const [educationLevel, setEducationLevel] = useState('')
  const [skillId, setSkillId] = useState('')
  const [level, setLevel] = useState<SkillLevel | ''>('')
  const [awardedOn, setAwardedOn] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<
    Partial<Record<Field, string>>
  >({})
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
          setSkillsError(
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

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const selected = skills.find((skill) => skill.id === skillId)
  const row = result?.rows[0]

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setResult(null)
    const problems: Partial<Record<Field, string>> = {}
    const firstProblem = nameError(firstName, 'First name')
    const lastProblem = nameError(lastName, 'Last name')
    const emailProblem = emailError(email)
    if (firstProblem) problems.firstName = firstProblem
    if (lastProblem) problems.lastName = lastProblem
    if (emailProblem) problems.email = emailProblem
    if (!skillId) {
      problems.skill =
        'Choose a skill. Every student row in the Sheet is a skill.'
    }
    setFieldErrors(problems)
    if (Object.keys(problems).length > 0) return
    if (!(level || asLevel(selected?.category ?? ''))) {
      setError('This skill has no level yet. Choose one.')
      return
    }
    try {
      setSubmitting(true)
      const response = await awardAdminSkill({
        skill_id: skillId,
        level: level || null,
        awarded_on: awardedOn || null,
        students: [
          {
            email: cleanEmail(email),
            first_name: cleanName(firstName),
            last_name: cleanName(lastName),
            program: program.trim(),
            education_level: educationLevel.trim(),
          },
        ],
      })
      setResult(response)
      if (response.rows[0]?.status === 'synced') onDone?.()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to add student')
    } finally {
      setSubmitting(false)
    }
  }

  const notice = result ? awardSyncNotice(result) : null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-student-title"
        className="bg-white rounded-2xl max-w-2xl w-full max-h-[92vh] overflow-y-auto p-6 shadow-xl border border-slate-200 space-y-5"
      >
        <div className="flex items-center justify-between">
          <h2
            id="add-student-title"
            className="text-lg font-bold text-slate-900"
          >
            Add student
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-slate-500 hover:text-slate-600 text-lg leading-none"
          >
            ✕
          </button>
        </div>

        <p className="text-xs text-slate-500">
          The student is added as a new row in the Google Sheet together with
          their first skill, then the sync runs. A Sheet row is always one skill
          award, so a skill is required.
        </p>

        {(error || skillsError) && (
          <div
            role="alert"
            className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs"
          >
            {error ?? skillsError}
          </div>
        )}

        {result && row ? (
          <div className="space-y-4">
            <div
              role="status"
              className={`p-4 rounded-xl border text-sm ${
                row.status === 'synced'
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                  : row.status === 'pending' || row.status === 'skipped'
                    ? 'bg-amber-50 border-amber-200 text-amber-900'
                    : 'bg-rose-50 border-rose-200 text-rose-800'
              }`}
            >
              {row.status === 'synced' && (
                <p>
                  Added. Passport{' '}
                  <span className="font-mono">{row.passport_id}</span>, version{' '}
                  {row.version}.
                </p>
              )}
              {row.status === 'pending' && (
                <p>
                  {notice ??
                    'Saved in the Sheet. It will sync shortly, then the student appears in the directory.'}
                </p>
              )}
              {row.status === 'skipped' && (
                <p>{adminErrorMessage(row.error)}</p>
              )}
              {row.status === 'failed' && (
                <p>
                  Not added: {adminErrorMessage(row.error)}{' '}
                  <span className="font-mono text-xs">({row.error})</span>
                </p>
              )}
            </div>
            <div className="flex items-center justify-end gap-3">
              {row.status === 'synced' && row.passport_id && (
                <Link
                  href={`/admin/students/${row.passport_id}`}
                  className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
                >
                  Open passport
                </Link>
              )}
              {row.status !== 'synced' && (
                <button
                  type="button"
                  onClick={() => setResult(null)}
                  className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-900"
                >
                  Back to the form
                </button>
              )}
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 bg-slate-900 text-white rounded-lg text-xs font-semibold hover:bg-slate-800"
              >
                Close
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="new-first-name"
                  className="block text-xs font-semibold text-slate-700 mb-1"
                >
                  First name *
                </label>
                <input
                  id="new-first-name"
                  type="text"
                  maxLength={100}
                  value={firstName}
                  onChange={(e) => {
                    setFirstName(e.target.value)
                    setFieldErrors((prev) => ({
                      ...prev,
                      firstName: undefined,
                    }))
                  }}
                  aria-invalid={Boolean(fieldErrors.firstName)}
                  aria-describedby="new-first-name-error"
                  className={inputClass}
                />
                <FieldError
                  id="new-first-name-error"
                  message={fieldErrors.firstName}
                />
              </div>
              <div>
                <label
                  htmlFor="new-last-name"
                  className="block text-xs font-semibold text-slate-700 mb-1"
                >
                  Last name *
                </label>
                <input
                  id="new-last-name"
                  type="text"
                  maxLength={100}
                  value={lastName}
                  onChange={(e) => {
                    setLastName(e.target.value)
                    setFieldErrors((prev) => ({ ...prev, lastName: undefined }))
                  }}
                  aria-invalid={Boolean(fieldErrors.lastName)}
                  aria-describedby="new-last-name-error"
                  className={inputClass}
                />
                <FieldError
                  id="new-last-name-error"
                  message={fieldErrors.lastName}
                />
              </div>
              <div className="sm:col-span-2">
                <label
                  htmlFor="new-email"
                  className="block text-xs font-semibold text-slate-700 mb-1"
                >
                  BTU email *
                </label>
                <input
                  id="new-email"
                  type="email"
                  placeholder="firstname.lastname@btu.edu.ge"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value)
                    setFieldErrors((prev) => ({ ...prev, email: undefined }))
                  }}
                  aria-invalid={Boolean(fieldErrors.email)}
                  aria-describedby="new-email-error"
                  className={inputClass}
                />
                <FieldError id="new-email-error" message={fieldErrors.email} />
                <p className="text-[11px] text-slate-500 mt-1">
                  University email only, at least 3 characters before @, not
                  just digits. Student ID and passport ID are assigned
                  automatically.
                </p>
              </div>
              <div>
                <label
                  htmlFor="new-education-level"
                  className="block text-xs font-semibold text-slate-700 mb-1"
                >
                  Education level
                </label>
                <select
                  id="new-education-level"
                  value={educationLevel}
                  onChange={(e) => {
                    setEducationLevel(e.target.value)
                    setProgram('')
                  }}
                  className={inputClass}
                >
                  <option value="">Choose a level...</option>
                  {EDUCATION_LEVELS.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </div>
              <div className="sm:col-span-2">
                <label
                  htmlFor="new-program"
                  className="block text-xs font-semibold text-slate-700 mb-1"
                >
                  Program
                </label>
                <select
                  id="new-program"
                  value={program}
                  disabled={!educationLevel}
                  onChange={(e) => setProgram(e.target.value)}
                  className={`${inputClass} disabled:opacity-60`}
                >
                  <option value="">
                    {educationLevel
                      ? 'Choose a program...'
                      : 'Choose an education level first'}
                  </option>
                  {programsForLevel(educationLevel).map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="border-t border-slate-100 pt-4 space-y-3">
              <h3 className="text-sm font-semibold text-slate-900">
                First skill (required)
              </h3>
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="sm:col-span-3">
                  <label
                    htmlFor="new-skill"
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Skill *
                  </label>
                  <select
                    id="new-skill"
                    value={skillId}
                    onChange={(e) => {
                      setSkillId(e.target.value)
                      setFieldErrors((prev) => ({ ...prev, skill: undefined }))
                    }}
                    aria-invalid={Boolean(fieldErrors.skill)}
                    aria-describedby="new-skill-error"
                    className={inputClass}
                  >
                    <option value="">Choose a skill...</option>
                    {skills.map((skill) => (
                      <option key={skill.id} value={skill.id}>
                        {skill.id} {skill.name}
                      </option>
                    ))}
                  </select>
                  <FieldError
                    id="new-skill-error"
                    message={fieldErrors.skill}
                  />
                </div>
                <div className="sm:col-span-2">
                  <label
                    htmlFor="new-level"
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Level
                  </label>
                  <select
                    id="new-level"
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
                    htmlFor="new-date"
                    className="block text-xs font-semibold text-slate-700 mb-1"
                  >
                    Date earned
                  </label>
                  <input
                    id="new-date"
                    type="date"
                    value={awardedOn}
                    onChange={(e) => setAwardedOn(e.target.value)}
                    className={inputClass}
                  />
                  <p className="text-[11px] text-slate-500 mt-1">
                    Leave empty to use today&apos;s date
                  </p>
                </div>
              </div>
              <p className="text-[11px] text-slate-500">
                Missing a skill? Create it on the{' '}
                <Link
                  href="/admin/skills"
                  className="text-indigo-600 underline hover:text-indigo-800"
                >
                  Skills Catalog
                </Link>{' '}
                page first.
              </p>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-900"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-sm"
              >
                {submitting ? 'Adding and syncing...' : 'Add student'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
