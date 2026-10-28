import { readAccessToken } from '@/lib/supabase/client'

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

export type SkillLevel = 'AI Skill' | 'AI Applied Skill' | 'AI Advanced Skill'

export const SKILL_LEVELS: SkillLevel[] = [
  'AI Skill',
  'AI Applied Skill',
  'AI Advanced Skill',
]

export interface AdminCatalogSkill {
  id: string
  name: string
  name_ka: string
  category: string
  badge: string
  description: string
}

export interface AdminCatalogSkillInput {
  name: string
  name_ka: string
  category: SkillLevel
  description: string
}

export interface AwardStudentInput {
  email: string
  first_name: string
  last_name: string
}

export interface AwardRowResult {
  email: string
  status: 'synced' | 'failed' | 'pending' | 'skipped'
  error: string
  passport_id: string
  version: string
}

export interface AdminAwardResponse {
  rows: AwardRowResult[]
  sync_result: {
    status: 'completed' | 'skipped' | 'failed'
    rows_read: number
    versions_created: number
    error: string | null
  }
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

async function getHeaders(): Promise<HeadersInit> {
  // The signed-in Supabase session decides who is an admin. The demo token only
  // works against a backend that has no Supabase configured (local demo).
  const token =
    (await readAccessToken()) ??
    (process.env.NEXT_PUBLIC_SUPABASE_URL ? '' : 'demo-admin')
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
    headers: await getHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to load students: ${res.statusText}`)
  return res.json()
}

export async function fetchAdminStudent(
  passportId: string,
): Promise<AdminStudentDetail> {
  const res = await fetch(
    `${API_BASE}/admin/students/${encodeURIComponent(passportId)}`,
    {
      headers: await getHeaders(),
    },
  )
  if (!res.ok) throw new Error(`Failed to load student: ${res.statusText}`)
  return res.json()
}

export async function deleteAdminStudent(passportId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/admin/students/${encodeURIComponent(passportId)}`,
    {
      method: 'DELETE',
      headers: await getHeaders(),
    },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.code || `Failed to delete student`)
  }
}

export async function addAdminSkill(
  passportId: string,
  skill: { skill: string; badge?: string; awarded_on?: string | null },
): Promise<AdminStudentDetail> {
  const res = await fetch(
    `${API_BASE}/admin/students/${encodeURIComponent(passportId)}/skills`,
    {
      method: 'POST',
      headers: await getHeaders(),
      body: JSON.stringify(skill),
    },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.code || `Failed to add skill`)
  }
  return res.json()
}

export async function removeAdminSkill(
  passportId: string,
  skillId: string,
): Promise<AdminStudentDetail> {
  const res = await fetch(
    `${API_BASE}/admin/students/${encodeURIComponent(passportId)}/skills/${encodeURIComponent(skillId)}`,
    {
      method: 'DELETE',
      headers: await getHeaders(),
    },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.code || `Failed to remove skill`)
  }
  return res.json()
}

export async function fetchAdminSyncRuns(
  limit = 50,
): Promise<AdminSyncRunList> {
  const res = await fetch(`${API_BASE}/admin/sync-runs?limit=${limit}`, {
    headers: await getHeaders(),
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
    headers: await getHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to trigger sync: ${res.statusText}`)
  return res.json()
}

export async function fetchAdminPendingVersions(): Promise<AdminVersionPendingList> {
  const res = await fetch(`${API_BASE}/admin/versions/pending`, {
    headers: await getHeaders(),
  })
  if (!res.ok)
    throw new Error(`Failed to load pending versions: ${res.statusText}`)
  return res.json()
}

export async function retryAdminAnchor(
  versionId: string,
): Promise<{ status: string }> {
  const res = await fetch(
    `${API_BASE}/admin/versions/${encodeURIComponent(versionId)}/anchor`,
    {
      method: 'POST',
      headers: await getHeaders(),
    },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.code || `Failed to retry anchor`)
  }
  return res.json()
}

const ERROR_MESSAGES: Record<string, string> = {
  skill_name_taken: 'A skill with this name already exists.',
  skill_not_found: 'That skill was not found.',
  sheet_unavailable:
    'The Google Sheet could not be reached. Nothing was saved. Try again in a minute.',
  award_level_required: 'Choose a level for this award.',
  unauthorized: 'Please sign in with your BTU account.',
  domain_not_allowed: 'Only BTU accounts can use the admin panel.',
  admin_not_found: 'Your account is not on the admin list.',
  email_domain_not_allowed: 'Email domain is not allowed.',
  invalid_email: 'Not a valid email address.',
  missing_full_name: 'New student: add a first and last name.',
  already_awarded: 'Already has this skill.',
  passport_id_taken: 'Passport ID already belongs to another student.',
}

export function adminErrorMessage(code: string): string {
  return ERROR_MESSAGES[code] ?? code
}

async function failure(res: Response, fallback: string): Promise<Error> {
  const err = await res.json().catch(() => ({}))
  return new Error(adminErrorMessage(err.code ?? fallback))
}

export async function fetchAdminSkills(): Promise<AdminCatalogSkill[]> {
  const res = await fetch(`${API_BASE}/admin/skills`, {
    headers: await getHeaders(),
  })
  if (!res.ok) throw await failure(res, 'Failed to load skills')
  const body: { skills: AdminCatalogSkill[] } = await res.json()
  return body.skills
}

export async function createAdminCatalogSkill(
  input: AdminCatalogSkillInput,
): Promise<AdminCatalogSkill> {
  const res = await fetch(`${API_BASE}/admin/skills`, {
    method: 'POST',
    headers: await getHeaders(),
    body: JSON.stringify(input),
  })
  if (!res.ok) throw await failure(res, 'Failed to create skill')
  return res.json()
}

export async function updateAdminCatalogSkill(
  id: string,
  input: Partial<AdminCatalogSkillInput>,
): Promise<AdminCatalogSkill> {
  const res = await fetch(
    `${API_BASE}/admin/skills/${encodeURIComponent(id)}`,
    {
      method: 'PATCH',
      headers: await getHeaders(),
      body: JSON.stringify(input),
    },
  )
  if (!res.ok) throw await failure(res, 'Failed to update skill')
  return res.json()
}

export async function awardAdminSkill(input: {
  skill_id: string
  level: SkillLevel | null
  awarded_on: string | null
  students: AwardStudentInput[]
}): Promise<AdminAwardResponse> {
  const res = await fetch(`${API_BASE}/admin/awards`, {
    method: 'POST',
    headers: await getHeaders(),
    body: JSON.stringify(input),
  })
  if (!res.ok) throw await failure(res, 'Failed to award skill')
  return res.json()
}

export function parseAwardStudents(text: string): AwardStudentInput[] {
  // One student per line: "email" or "email, First Last". A line with several
  // emails adds each of them without a name.
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .flatMap((line): AwardStudentInput[] => {
      const tokens = line.split(/[\s,;]+/).filter(Boolean)
      const emails = tokens.filter((token) => token.includes('@'))
      const [email, ...others] = emails
      if (email === undefined) {
        return [{ email: line, first_name: '', last_name: '' }]
      }
      if (others.length > 0) {
        return emails.map((item) => ({
          email: item,
          first_name: '',
          last_name: '',
        }))
      }
      const [first = '', ...last] = tokens.filter(
        (token) => !token.includes('@'),
      )
      return [{ email, first_name: first, last_name: last.join(' ') }]
    })
}
