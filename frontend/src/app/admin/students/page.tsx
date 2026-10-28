'use client'

import Link from 'next/link'
import React, { useEffect, useState } from 'react'
import { AddStudentDialog } from '@/components/admin/add-student-dialog'
import {
  fetchAdminStudents,
  deleteAdminStudent,
  type AdminStudent,
} from '@/lib/api/admin'

export default function AdminStudentsPage() {
  const [students, setStudents] = useState<AdminStudent[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [tab, setTab] = useState<'all' | 'admin' | 'archived'>('all')

  const loadStudents = async () => {
    setLoading(true)
    try {
      const data = await fetchAdminStudents({
        search: search.trim() || undefined,
        includeDeleted: tab === 'archived',
        limit: 100,
      })
      let filtered = data.students
      if (tab === 'admin') {
        filtered = filtered.filter((s) => s.admin_managed && !s.deleted_at)
      } else if (tab === 'all') {
        filtered = filtered.filter((s) => !s.deleted_at)
      } else if (tab === 'archived') {
        filtered = filtered.filter((s) => s.deleted_at !== null)
      }
      setStudents(filtered)
    } catch (err: unknown) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let ignore = false
    async function init() {
      try {
        const data = await fetchAdminStudents({
          includeDeleted: tab === 'archived',
          limit: 100,
        })
        if (!ignore) {
          let filtered = data.students
          if (tab === 'admin') {
            filtered = filtered.filter((s) => s.admin_managed && !s.deleted_at)
          } else if (tab === 'all') {
            filtered = filtered.filter((s) => !s.deleted_at)
          } else if (tab === 'archived') {
            filtered = filtered.filter((s) => s.deleted_at !== null)
          }
          setStudents(filtered)
        }
      } catch (err: unknown) {
        if (!ignore) {
          console.error(err)
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
  }, [tab])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    loadStudents()
  }

  const handleDelete = async (passportId: string, name: string) => {
    if (
      !confirm(
        `Are you sure you want to archive student ${name}? This will preserve historical records but prevent new access.`,
      )
    ) {
      return
    }
    try {
      await deleteAdminStudent(passportId)
      await loadStudents()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to delete student')
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Student Directory
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Students and passports come from the Google Sheet. Add students by
            awarding them a skill.
          </p>
        </div>
        <div className="flex items-center gap-3 self-start sm:self-auto">
          <Link
            href="/admin/awards"
            className="px-4 py-2 text-sm font-medium text-slate-700 hover:text-slate-900"
          >
            Award a skill
          </Link>
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 4v16m8-8H4"
              />
            </svg>
            Add student
          </button>
        </div>
      </div>

      {/* Tabs & Search Filter */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-3 rounded-2xl border border-slate-200/80 shadow-xs">
        {/* Tabs */}
        <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl">
          <button
            onClick={() => setTab('all')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
              tab === 'all'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            All Active
          </button>
          <button
            onClick={() => setTab('admin')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
              tab === 'admin'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Admin Managed Only
          </button>
          <button
            onClick={() => setTab('archived')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
              tab === 'archived'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Archived / Soft-Deleted
          </button>
        </div>

        {/* Search Input */}
        <form
          onSubmit={handleSearchSubmit}
          className="flex items-center gap-2 max-w-sm w-full"
        >
          <div className="relative flex-1">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name or email..."
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
            />
            <svg
              className="w-4 h-4 text-slate-400 absolute left-3 top-2.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
          </div>
          <button
            type="submit"
            className="px-3 py-1.5 bg-slate-900 text-white rounded-lg text-xs font-medium hover:bg-slate-800 transition-colors"
          >
            Filter
          </button>
        </form>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider border-b border-slate-100">
              <tr>
                <th className="px-6 py-3 font-semibold">Student Name</th>
                <th className="px-6 py-3 font-semibold">Email</th>
                <th className="px-6 py-3 font-semibold">
                  Permanent Passport ID
                </th>
                <th className="px-6 py-3 font-semibold">Source</th>
                <th className="px-6 py-3 font-semibold">Versions</th>
                <th className="px-6 py-3 font-semibold">Latest Anchor</th>
                <th className="px-6 py-3 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td
                    colSpan={7}
                    className="px-6 py-12 text-center text-slate-400 text-xs"
                  >
                    Loading student directory...
                  </td>
                </tr>
              ) : students.length === 0 ? (
                <tr>
                  <td
                    colSpan={7}
                    className="px-6 py-12 text-center text-slate-400 text-xs"
                  >
                    No students found matching your criteria.
                  </td>
                </tr>
              ) : (
                students.map((student) => (
                  <tr
                    key={student.id}
                    className="hover:bg-slate-50/60 transition-colors"
                  >
                    <td className="px-6 py-4 font-medium text-slate-900">
                      <Link
                        href={`/admin/students/${student.passport_id}`}
                        className="hover:text-indigo-600 transition-colors flex items-center gap-2 group"
                      >
                        {student.full_name}
                        <span className="text-slate-300 group-hover:text-indigo-500 transition-colors">
                          →
                        </span>
                      </Link>
                    </td>
                    <td className="px-6 py-4 text-xs font-mono text-slate-600">
                      {student.email}
                    </td>
                    <td className="px-6 py-4">
                      <span className="font-mono text-xs px-2 py-0.5 rounded-md bg-slate-100 text-slate-800 border border-slate-200">
                        {student.passport_id}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs">
                      {student.admin_managed ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-purple-50 text-purple-700 border border-purple-200">
                          Admin Managed
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-blue-50 text-blue-700 border border-blue-200">
                          Google Sheet
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-xs font-mono font-medium text-slate-700">
                      {student.version_count} v
                    </td>
                    <td className="px-6 py-4 text-xs">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium capitalize ${
                          student.latest_anchor_status === 'confirmed'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : student.latest_anchor_status === 'pending'
                              ? 'bg-amber-50 text-amber-700 border border-amber-200'
                              : 'bg-rose-50 text-rose-700 border border-rose-200'
                        }`}
                      >
                        {student.latest_anchor_status ?? 'N/A'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right text-xs space-x-2">
                      <Link
                        href={`/admin/students/${student.passport_id}`}
                        className="text-indigo-600 hover:text-indigo-800 font-medium transition-colors"
                      >
                        View Details
                      </Link>
                      {!student.deleted_at && (
                        <>
                          <span className="text-slate-300">|</span>
                          <button
                            onClick={() =>
                              handleDelete(
                                student.passport_id,
                                student.full_name,
                              )
                            }
                            className="text-rose-600 hover:text-rose-800 font-medium transition-colors"
                          >
                            Archive
                          </button>
                        </>
                      )}
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
          onDone={() => void loadStudents()}
        />
      )}
    </div>
  )
}
