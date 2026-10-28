'use client'

import Link from 'next/link'
import React, { useEffect, useState } from 'react'
import {
  SKILL_LEVELS,
  createAdminCatalogSkill,
  fetchAdminSkills,
  updateAdminCatalogSkill,
  type AdminCatalogSkill,
  type SkillLevel,
} from '@/lib/api/admin'

interface FormState {
  id: string | null
  name: string
  name_ka: string
  category: SkillLevel
  description: string
}

const EMPTY_FORM: FormState = {
  id: null,
  name: '',
  name_ka: '',
  category: 'AI Skill',
  description: '',
}

const inputClass =
  'w-full px-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500'

function asLevel(value: string): SkillLevel {
  return SKILL_LEVELS.find((level) => level === value) ?? 'AI Skill'
}

export default function AdminSkillsPage() {
  const [skills, setSkills] = useState<AdminCatalogSkill[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [formError, setFormError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [filter, setFilter] = useState('')

  useEffect(() => {
    let ignore = false
    async function load() {
      try {
        const data = await fetchAdminSkills()
        if (ignore) return
        setSkills(data)
        setLoadError(null)
      } catch (err: unknown) {
        if (ignore) return
        setLoadError(
          err instanceof Error ? err.message : 'Failed to load skills',
        )
      } finally {
        if (!ignore) setLoading(false)
      }
    }
    void load()
    return () => {
      ignore = true
    }
  }, [reload])

  const editing = form.id !== null

  const startEdit = (skill: AdminCatalogSkill) => {
    setNotice(null)
    setFormError(null)
    setForm({
      id: skill.id,
      name: skill.name,
      name_ka: skill.name_ka,
      category: asLevel(skill.category),
      description: skill.description,
    })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const reset = () => {
    setForm(EMPTY_FORM)
    setFormError(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setNotice(null)
    const name = form.name.trim()
    if (!name) {
      setFormError('Please enter the English skill name.')
      return
    }
    const input = {
      name,
      name_ka: form.name_ka.trim(),
      category: form.category,
      description: form.description.trim(),
    }
    try {
      setSaving(true)
      const saved = form.id
        ? await updateAdminCatalogSkill(form.id, input)
        : await createAdminCatalogSkill(input)
      setNotice(
        form.id
          ? `${saved.id} updated in the Sheet and the database.`
          : `${saved.id} added to the Skills tab and the database.`,
      )
      setForm(EMPTY_FORM)
      setLoading(true)
      setReload((count) => count + 1)
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : 'Failed to save skill')
    } finally {
      setSaving(false)
    }
  }

  const shown = skills.filter((skill) => {
    const needle = filter.trim().toLowerCase()
    if (!needle) return true
    return (
      skill.id.toLowerCase().includes(needle) ||
      skill.name.toLowerCase().includes(needle) ||
      skill.name_ka.toLowerCase().includes(needle)
    )
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Skills Catalog
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Skills are saved to the Skills tab of the Google Sheet first, then to
          the database. Award them to students from the Award Skills page.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5 space-y-4"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-900">
            {editing ? `Edit ${form.id}` : 'Create a skill'}
          </h2>
          {editing && (
            <button
              type="button"
              onClick={reset}
              className="text-xs font-medium text-slate-500 hover:text-slate-900"
            >
              Cancel edit
            </button>
          )}
        </div>

        {formError && (
          <div
            role="alert"
            className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs"
          >
            {formError}
          </div>
        )}
        {notice && (
          <div
            role="status"
            className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs"
          >
            {notice}
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label
              htmlFor="skill-name"
              className="block text-xs font-semibold text-slate-700 mb-1"
            >
              Name (English)
            </label>
            <input
              id="skill-name"
              type="text"
              required
              maxLength={200}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Data Storytelling with AI"
              className={inputClass}
            />
          </div>
          <div>
            <label
              htmlFor="skill-name-ka"
              className="block text-xs font-semibold text-slate-700 mb-1"
            >
              Name (Georgian)
            </label>
            <input
              id="skill-name-ka"
              type="text"
              maxLength={200}
              value={form.name_ka}
              onChange={(e) => setForm({ ...form, name_ka: e.target.value })}
              placeholder="ქართული სახელი"
              className={inputClass}
            />
          </div>
          <div>
            <label
              htmlFor="skill-level"
              className="block text-xs font-semibold text-slate-700 mb-1"
            >
              Level
            </label>
            <select
              id="skill-level"
              value={form.category}
              onChange={(e) =>
                setForm({ ...form, category: asLevel(e.target.value) })
              }
              className={inputClass}
            >
              {SKILL_LEVELS.map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>
            <p className="text-[11px] text-slate-400 mt-1">
              The level decides the badge: AI Skill, AI Applied Skill or AI
              Advanced Skill.
            </p>
          </div>
          <div className="md:row-span-2">
            <label
              htmlFor="skill-description"
              className="block text-xs font-semibold text-slate-700 mb-1"
            >
              Description
            </label>
            <textarea
              id="skill-description"
              rows={4}
              maxLength={1000}
              value={form.description}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
              placeholder="One or two sentences shown on the passport."
              className={inputClass}
            />
          </div>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-sm"
          >
            {saving ? 'Saving...' : editing ? 'Save changes' : 'Create skill'}
          </button>
        </div>
      </form>

      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
        <div className="flex items-center justify-between gap-3 p-4 border-b border-slate-100">
          <h2 className="text-base font-semibold text-slate-900">
            All skills ({skills.length})
          </h2>
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by id or name..."
            aria-label="Filter skills"
            className="max-w-xs w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider border-b border-slate-100">
              <tr>
                <th className="px-6 py-3 font-semibold">ID</th>
                <th className="px-6 py-3 font-semibold">Name</th>
                <th className="px-6 py-3 font-semibold">Georgian</th>
                <th className="px-6 py-3 font-semibold">Level</th>
                <th className="px-6 py-3 font-semibold">Description</th>
                <th className="px-6 py-3 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-6 py-12 text-center text-slate-400 text-xs"
                  >
                    Loading skills...
                  </td>
                </tr>
              ) : loadError ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-6 py-12 text-center text-rose-600 text-xs"
                  >
                    {loadError}
                  </td>
                </tr>
              ) : shown.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-6 py-12 text-center text-slate-400 text-xs"
                  >
                    No skills yet. Create the first one above.
                  </td>
                </tr>
              ) : (
                shown.map((skill) => (
                  <tr
                    key={skill.id}
                    className="hover:bg-slate-50/60 transition-colors"
                  >
                    <td className="px-6 py-4 font-mono text-xs text-slate-700">
                      {skill.id}
                    </td>
                    <td className="px-6 py-4 font-medium text-slate-900">
                      {skill.name}
                    </td>
                    <td className="px-6 py-4 text-slate-600">
                      {skill.name_ka || (
                        <span className="text-slate-300">none</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-xs">
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-indigo-50 text-indigo-700 border border-indigo-200">
                        {skill.category || 'No level'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500 max-w-xs truncate">
                      {skill.description}
                    </td>
                    <td className="px-6 py-4 text-right text-xs space-x-2 whitespace-nowrap">
                      <button
                        type="button"
                        onClick={() => startEdit(skill)}
                        className="text-indigo-600 hover:text-indigo-800 font-medium"
                      >
                        Edit
                      </button>
                      <span className="text-slate-300">|</span>
                      <Link
                        href={`/admin/awards?skill=${encodeURIComponent(skill.id)}`}
                        className="text-indigo-600 hover:text-indigo-800 font-medium"
                      >
                        Award
                      </Link>
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
