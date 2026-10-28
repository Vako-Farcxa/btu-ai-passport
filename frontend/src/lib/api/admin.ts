export interface AdminSkillEntry {
  id: string
  skill: string
  badge: string
  awarded_on: string | null
  description: string
  position: number
}

export interface AdminVersion {
  id: string
  version_number: number
  holder_name: string
  verification_code: string
  anchor_status: 'pending' | 'confirmed' | 'failed'
  tx_hash: string | null
  issued_at: string
  pdf_en_path: string | null
  pdf_ka_path: string | null
  skills: AdminSkillEntry[]
}

export interface AdminStudent {
  id: string
  email: string
  full_name: string
  passport_id: string
  admin_managed: boolean
  deleted_at: string | null
  version_count: number
  latest_anchor_status: 'pending' | 'confirmed' | 'failed' | null
  created_at: string
}

export interface AdminStudentDetail {
  id: string
  email: string
  full_name: string
  passport_id: string
  admin_managed: boolean
  deleted_at: string | null
  created_at: string
  versions: AdminVersion[]
}

export interface AdminStudentList {
  students: AdminStudent[]
  total: number
}

export interface AdminSyncRun {
  id: string
  status: 'running' | 'completed' | 'skipped' | 'failed'
  started_at: string
  finished_at: string | null
  rows_read: number | null
  versions_created: number | null
  error: string | null
}

export interface AdminSyncRunList {
  runs: AdminSyncRun[]
}

export interface AdminVersionPending {
  version_id: string
  passport_id: string
  holder_name: string
  version_number: number
  anchor_status: 'pending' | 'failed'
  issued_at: string
  tx_hash: string | null
}

export interface AdminVersionPendingList {
  versions: AdminVersionPending[]
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

function getHeaders(): HeadersInit {
  // Use demo-admin token locally or read from sessionStorage/cookie if available
  const token =
    typeof window !== 'undefined'
      ? window.localStorage.getItem('admin_token') || 'demo-admin'
      : 'demo-admin'

  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  }
}

export async function fetchAdminStudents(params?: {
  search?: string
  includeDeleted?: boolean
  offset?: number
  limit?: number
}): Promise<AdminStudentList> {
  const query = new URLSearchParams()
  if (params?.search) query.set('search', params.search)
  if (params?.includeDeleted) query.set('include_deleted', 'true')
  if (params?.offset !== undefined) query.set('offset', String(params.offset))
  if (params?.limit !== undefined) query.set('limit', String(params.limit))

  const res = await fetch(`${API_BASE}/admin/students?${query.toString()}`, {
    headers: getHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to load students: ${res.statusText}`)
  return res.json()
}

export async function fetchAdminStudent(passportId: string): Promise<AdminStudentDetail> {
  const res = await fetch(`${API_BASE}/admin/students/${encodeURIComponent(passportId)}`, {
    headers: getHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to load student: ${res.statusText}`)
  return res.json()
}

export async function createAdminStudent(data: {
  email: string
  full_name: string
}): Promise<AdminStudentDetail> {
  const res = await fetch(`${API_BASE}/admin/students`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.code || `Failed to create student`)
  }
  return res.json()
}

export async function deleteAdminStudent(passportId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/admin/students/${encodeURIComponent(passportId)}`, {
    method: 'DELETE',
    headers: getHeaders(),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.code || `Failed to delete student`)
  }
}

export async function addAdminSkill(
  passportId: string,
  skill: { skill: string; badge?: string; awarded_on?: string | null }
): Promise<AdminStudentDetail> {
  const res = await fetch(
    `${API_BASE}/admin/students/${encodeURIComponent(passportId)}/skills`,
    {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(skill),
    }
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.code || `Failed to add skill`)
  }
  return res.json()
}

export async function removeAdminSkill(
  passportId: string,
  skillId: string
): Promise<AdminStudentDetail> {
  const res = await fetch(
    `${API_BASE}/admin/students/${encodeURIComponent(passportId)}/skills/${encodeURIComponent(skillId)}`,
    {
      method: 'DELETE',
      headers: getHeaders(),
    }
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.code || `Failed to remove skill`)
  }
  return res.json()
}

export async function fetchAdminSyncRuns(limit = 50): Promise<AdminSyncRunList> {
  const res = await fetch(`${API_BASE}/admin/sync-runs?limit=${limit}`, {
    headers: getHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to load sync runs: ${res.statusText}`)
  return res.json()
}

export async function triggerAdminSync(): Promise<{
  status: string
  rows_read: number
  versions_created: number
}> {
  const res = await fetch(`${API_BASE}/admin/sync`, {
    method: 'POST',
    headers: getHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to trigger sync: ${res.statusText}`)
  return res.json()
}

export async function fetchAdminPendingVersions(): Promise<AdminVersionPendingList> {
  const res = await fetch(`${API_BASE}/admin/versions/pending`, {
    headers: getHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to load pending versions: ${res.statusText}`)
  return res.json()
}

export async function retryAdminAnchor(versionId: string): Promise<{ status: string }> {
  const res = await fetch(
    `${API_BASE}/admin/versions/${encodeURIComponent(versionId)}/anchor`,
    {
      method: 'POST',
      headers: getHeaders(),
    }
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.code || `Failed to retry anchor`)
  }
  return res.json()
}
