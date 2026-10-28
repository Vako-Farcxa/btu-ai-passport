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
  // Only used for students who are not in the Sheet yet.
  program?: string
  education_level?: string
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

export class AdminAccessError extends Error {
  readonly code: 'signed_out' | 'not_authorized'

  constructor(code: 'signed_out' | 'not_authorized') {
    super(code)
    this.name = 'AdminAccessError'
    this.code = code
  }
}

async function getHeaders(): Promise<HeadersInit> {
  // Only the signed-in Supabase session is accepted. There is no demo token and no
  // fallback: without a session nothing is sent to the API.
  const token = await readAccessToken()
  if (!token) throw new AdminAccessError('signed_out')
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  }
}

/** Asks the backend whether the signed-in user is an admin. Never guesses. */
export async function fetchAdminMe(): Promise<{ email: string }> {
  const res = await fetch(`${API_BASE}/admin/me`, {
    headers: await getHeaders(),
    cache: 'no-store',
  })
  if (res.status === 401) throw new AdminAccessError('signed_out')
  if (res.status === 403) throw new AdminAccessError('not_authorized')
  if (!res.ok) throw new Error(`Failed to check admin access: ${res.status}`)
  const body: unknown = await res.json()
  if (
    typeof body !== 'object' ||
    body === null ||
    !('email' in body) ||
    typeof body.email !== 'string'
  ) {
    throw new Error('Unexpected admin response')
  }
  return { email: body.email }
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

export async function fetchAdminSyncRuns(
  limit = 50,
): Promise<AdminSyncRunList> {
  const res = await fetch(`${API_BASE}/admin/sync-runs?limit=${limit}`, {
    headers: await getHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to load sync runs: ${res.statusText}`)
  return res.json()
}

export interface AdminSyncResult {
  status: 'completed' | 'skipped' | 'failed'
  rows_read: number
  versions_created: number
  error?: string | null
}

export interface SyncNotice {
  kind: 'success' | 'warning' | 'error'
  text: string
}

/** Honest one-line summary of a manual sync, by its real outcome. */
export function describeSyncResult(res: AdminSyncResult): SyncNotice {
  if (res.status === 'completed') {
    return {
      kind: 'success',
      text: `Sync completed. Rows read: ${res.rows_read}, new versions created: ${res.versions_created}.`,
    }
  }
  if (res.status === 'skipped') {
    return {
      kind: 'warning',
      text: 'Sync skipped: another sync is already running. Nothing was read. Try again in a minute.',
    }
  }
  return {
    kind: 'error',
    text: `Sync failed${res.error ? `: ${res.error}` : ''}. Rows read: ${res.rows_read}, new versions created: ${res.versions_created}.`,
  }
}

export async function triggerAdminSync(): Promise<AdminSyncResult> {
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
  email_local_too_short: 'The part before @ needs at least 3 characters.',
  email_local_not_name_like: 'The part before @ cannot be only digits.',
  invalid_first_name:
    'First name must be 2 to 50 letters (Latin or Georgian). No digits or symbols.',
  invalid_last_name:
    'Last name must be 2 to 50 letters (Latin or Georgian). No digits or symbols.',
  duplicate_email: 'The same email is listed more than once.',
  invalid_comment: 'The note must be 500 characters or fewer.',
  flag_not_found: 'That flag no longer exists.',
  missing_full_name: 'New student: add a first and last name.',
  already_awarded: 'Already has this skill.',
  passport_id_taken: 'Passport ID already belongs to another student.',
  student_conflict:
    'This email already exists in the database in a way the sync could not merge. Ask a developer to check it.',
  sync_error: 'The sync could not process this student. Try again later.',
  missing_skill: 'A skill is required.',
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

/** Plain-words note about the sync that ran after an award, or null when all is well. */
export function awardSyncNotice(result: AdminAwardResponse): string | null {
  const { status, error } = result.sync_result
  if (status === 'skipped' && error === 'sync_in_progress') {
    return 'Another sync is running, your rows are saved and will sync shortly.'
  }
  if (status === 'failed') {
    return 'The sync failed after the rows were added to the Sheet. They will be picked up by the next scheduled sync.'
  }
  return null
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

// ---------------------------------------------------------------------------
// Student flags
// ---------------------------------------------------------------------------

export type AdminFlagStatus = 'open' | 'resolved' | 'dismissed'

export interface AdminFlag {
  id: string
  passport_id: string
  version: number
  verification_code: string
  student_email: string
  comment: string
  status: AdminFlagStatus
  admin_note: string
  resolved_by: string | null
  created_at: string
  resolved_at: string | null
}

export interface AdminFlagList {
  flags: AdminFlag[]
  open_count: number
}

export const FLAG_NOTE_MAX = 500

export async function fetchAdminFlags(
  status?: AdminFlagStatus,
): Promise<AdminFlagList> {
  const query = status ? `?status=${status}` : ''
  const res = await fetch(`${API_BASE}/admin/flags${query}`, {
    headers: await getHeaders(),
    cache: 'no-store',
  })
  if (!res.ok) throw await failure(res, 'Failed to load flags')
  return res.json()
}

export async function updateAdminFlag(
  id: string,
  input: { status: 'resolved' | 'dismissed'; admin_note: string },
): Promise<AdminFlag> {
  const res = await fetch(`${API_BASE}/admin/flags/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: await getHeaders(),
    body: JSON.stringify(input),
  })
  if (!res.ok) throw await failure(res, 'Failed to update the flag')
  return res.json()
}
