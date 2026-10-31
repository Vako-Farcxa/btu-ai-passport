import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AdminAccessError,
  createAdminCatalogSkill,
  deleteAdminStudent,
  awardAdminSkill,
  fetchAdminFlags,
  fetchAdminMe,
  fetchAdminPendingVersions,
  fetchAdminSkills,
  fetchAdminStudent,
  fetchAdminStudents,
  fetchAdminSyncRuns,
  retryAdminAnchor,
  triggerAdminSync,
  updateAdminCatalogSkill,
  updateAdminFlag,
} from '@/lib/api/admin'
import { RateLimitedError } from '@/lib/api/rate-limit'

const token = vi.hoisted(() => ({ value: 'tok' as string | null }))
vi.mock('@/lib/supabase/client', () => ({
  readAccessToken: async () => token.value,
}))

const API = 'http://localhost:8000'

function reply(status: number, body: unknown = {}, headers: HeadersInit = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: `status ${status}`,
    headers: new Headers(headers),
    json: async () => body,
  }
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  token.value = 'tok'
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

function lastCall() {
  const [url, init] = fetchMock.mock.calls.at(-1) as [
    string,
    RequestInit & { headers: Record<string, string> },
  ]
  return { url, init }
}

describe('every admin request', () => {
  const calls: [string, () => Promise<unknown>][] = [
    ['fetchAdminMe', () => fetchAdminMe()],
    ['fetchAdminStudents', () => fetchAdminStudents()],
    ['fetchAdminStudent', () => fetchAdminStudent('BTU-1')],
    ['deleteAdminStudent', () => deleteAdminStudent('BTU-1')],
    ['fetchAdminSyncRuns', () => fetchAdminSyncRuns()],
    ['triggerAdminSync', () => triggerAdminSync()],
    ['fetchAdminPendingVersions', () => fetchAdminPendingVersions()],
    ['retryAdminAnchor', () => retryAdminAnchor('v-1')],
    ['fetchAdminSkills', () => fetchAdminSkills()],
    ['fetchAdminFlags', () => fetchAdminFlags()],
  ]

  it.each(calls)(
    '%s sends nothing without a signed-in session',
    async (_n, call) => {
      token.value = null
      await expect(call()).rejects.toBeInstanceOf(AdminAccessError)
      expect(fetchMock).not.toHaveBeenCalled()
    },
  )

  it.each(calls)(
    '%s turns a 429 into the friendly wait message',
    async (_n, call) => {
      fetchMock.mockResolvedValue(reply(429, {}, { 'Retry-After': '42' }))
      const error = await call().catch((e: unknown) => e)
      expect(error).toBeInstanceOf(RateLimitedError)
      expect((error as RateLimitedError).retryAfter).toBe(42)
    },
  )

  it.each(calls)('%s sends the bearer token', async (_n, call) => {
    fetchMock.mockResolvedValue(reply(200, { email: 'a@btu.edu.ge' }))
    await call().catch(() => undefined)
    expect(lastCall().init.headers.Authorization).toBe('Bearer tok')
  })
})

describe('fetchAdminMe', () => {
  it('maps 401 and 403 to the two access errors', async () => {
    fetchMock.mockResolvedValueOnce(reply(401))
    await expect(fetchAdminMe()).rejects.toMatchObject({ code: 'signed_out' })
    fetchMock.mockResolvedValueOnce(reply(403))
    await expect(fetchAdminMe()).rejects.toMatchObject({
      code: 'not_authorized',
    })
  })

  it('throws on a server error and on a body without an email', async () => {
    fetchMock.mockResolvedValueOnce(reply(500))
    await expect(fetchAdminMe()).rejects.toThrow('500')
    for (const body of [null, 'x', {}, { email: 5 }]) {
      fetchMock.mockResolvedValueOnce(reply(200, body))
      await expect(fetchAdminMe()).rejects.toThrow('Unexpected admin response')
    }
  })

  it('returns the email', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { email: 'a@btu.edu.ge' }))
    await expect(fetchAdminMe()).resolves.toEqual({ email: 'a@btu.edu.ge' })
  })
})

describe('students', () => {
  it('builds the query from the filters that are set', async () => {
    fetchMock.mockResolvedValue(reply(200, { students: [], total: 0 }))
    await fetchAdminStudents({
      search: 'nino',
      includeDeleted: true,
      offset: 0,
      limit: 50,
    })
    expect(lastCall().url).toBe(
      `${API}/admin/students?search=nino&include_deleted=true&offset=0&limit=50`,
    )
    await fetchAdminStudents()
    expect(lastCall().url).toBe(`${API}/admin/students?`)
  })

  it('reads one student with the id escaped', async () => {
    fetchMock.mockResolvedValue(reply(200, { id: 's' }))
    await fetchAdminStudent('BTU 1/2')
    expect(lastCall().url).toBe(`${API}/admin/students/BTU%201%2F2`)
  })

  it('throws a readable error when the list or one student cannot load', async () => {
    fetchMock.mockResolvedValue(reply(500))
    await expect(fetchAdminStudents()).rejects.toThrow(
      'Failed to load students',
    )
    await expect(fetchAdminStudent('x')).rejects.toThrow(
      'Failed to load student',
    )
  })

  it('archives with DELETE and reports the API code or a fallback', async () => {
    fetchMock.mockResolvedValueOnce(reply(204))
    await deleteAdminStudent('BTU-1')
    expect(lastCall().init.method).toBe('DELETE')
    fetchMock.mockResolvedValueOnce(
      reply(409, { code: 'student_already_deleted' }),
    )
    await expect(deleteAdminStudent('BTU-1')).rejects.toThrow(
      'student_already_deleted',
    )
    fetchMock.mockResolvedValueOnce({
      ...reply(500),
      json: async () => {
        throw new Error('not json')
      },
    })
    await expect(deleteAdminStudent('BTU-1')).rejects.toThrow(
      'Failed to delete student',
    )
  })
})

describe('sync and anchoring', () => {
  it('asks for the sync history with a limit', async () => {
    fetchMock.mockResolvedValue(reply(200, { runs: [] }))
    await fetchAdminSyncRuns(10)
    expect(lastCall().url).toBe(`${API}/admin/sync-runs?limit=10`)
    fetchMock.mockResolvedValue(reply(500))
    await expect(fetchAdminSyncRuns()).rejects.toThrow(
      'Failed to load sync runs',
    )
  })

  it('triggers a sync with POST and fails loudly', async () => {
    fetchMock.mockResolvedValueOnce(
      reply(200, { status: 'completed', rows_read: 1, versions_created: 1 }),
    )
    await expect(triggerAdminSync()).resolves.toMatchObject({
      status: 'completed',
    })
    expect(lastCall().init.method).toBe('POST')
    fetchMock.mockResolvedValueOnce(reply(500))
    await expect(triggerAdminSync()).rejects.toThrow('Failed to trigger sync')
  })

  it('lists pending versions', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { versions: [] }))
    await fetchAdminPendingVersions()
    expect(lastCall().url).toBe(`${API}/admin/versions/pending`)
    fetchMock.mockResolvedValueOnce(reply(500))
    await expect(fetchAdminPendingVersions()).rejects.toThrow(
      'Failed to load pending versions',
    )
  })

  it('retries an anchor and explains a refusal in plain words', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { status: 'confirmed' }))
    await expect(retryAdminAnchor('v 1')).resolves.toEqual({
      status: 'confirmed',
    })
    expect(lastCall().url).toBe(`${API}/admin/versions/v%201/anchor`)
    fetchMock.mockResolvedValueOnce(reply(409, { code: 'anchor_busy' }))
    await expect(retryAdminAnchor('v-1')).rejects.toThrow(
      'Another anchoring run is in progress',
    )
    fetchMock.mockResolvedValueOnce({
      ...reply(500),
      json: async () => {
        throw new Error('not json')
      },
    })
    await expect(retryAdminAnchor('v-1')).rejects.toThrow(
      'Failed to retry anchoring',
    )
  })
})

describe('skills, awards and flags', () => {
  it('lists, creates and updates catalog skills', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { skills: [{ id: 'SKL-1' }] }))
    await expect(fetchAdminSkills()).resolves.toEqual([{ id: 'SKL-1' }])

    fetchMock.mockResolvedValueOnce(reply(201, { id: 'SKL-2' }))
    const input = {
      name: 'SQL',
      name_ka: 'SQL',
      category: 'AI Skill',
      description: 'Queries',
    } as never
    await createAdminCatalogSkill(input)
    expect(lastCall().init.method).toBe('POST')
    expect(JSON.parse(String(lastCall().init.body))).toMatchObject({
      name: 'SQL',
    })

    fetchMock.mockResolvedValueOnce(reply(200, { id: 'SKL-2' }))
    await updateAdminCatalogSkill('SKL-2', { name: 'SQL 2' })
    expect(lastCall().url).toBe(`${API}/admin/skills/SKL-2`)
    expect(lastCall().init.method).toBe('PATCH')
  })

  it('shows the plain sentence for a catalog error code', async () => {
    fetchMock.mockResolvedValue(reply(409, { code: 'skill_name_taken' }))
    await expect(createAdminCatalogSkill({} as never)).rejects.toThrow(
      'already exists',
    )
    await expect(updateAdminCatalogSkill('SKL-1', {})).rejects.toThrow(
      'already exists',
    )
    fetchMock.mockResolvedValue(reply(500, 'not an object'))
    await expect(fetchAdminSkills()).rejects.toThrow()
  })

  it('posts an award and reports a refusal', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { rows: [], sync_result: {} }))
    await awardAdminSkill({
      skill_id: 'SKL-1',
      level: null,
      awarded_on: null,
      students: [],
    })
    expect(lastCall().url).toBe(`${API}/admin/awards`)
    fetchMock.mockResolvedValueOnce(
      reply(409, { code: 'award_level_required' }),
    )
    await expect(
      awardAdminSkill({
        skill_id: 'SKL-1',
        level: null,
        awarded_on: null,
        students: [],
      }),
    ).rejects.toThrow('Choose a level')
  })

  it('filters flags by status and sends the reply on PATCH', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { flags: [], open_count: 0 }))
    await fetchAdminFlags('open')
    expect(lastCall().url).toBe(`${API}/admin/flags?status=open`)
    fetchMock.mockResolvedValueOnce(reply(200, { flags: [], open_count: 0 }))
    await fetchAdminFlags()
    expect(lastCall().url).toBe(`${API}/admin/flags`)

    fetchMock.mockResolvedValueOnce(reply(200, { id: 'f1' }))
    await updateAdminFlag('f 1', { status: 'resolved', admin_note: 'Done' })
    expect(lastCall().url).toBe(`${API}/admin/flags/f%201`)
    expect(lastCall().init.method).toBe('PATCH')
    expect(JSON.parse(String(lastCall().init.body))).toEqual({
      status: 'resolved',
      admin_note: 'Done',
    })

    fetchMock.mockResolvedValueOnce(reply(404, { code: 'flag_not_found' }))
    await expect(
      updateAdminFlag('f1', { status: 'dismissed', admin_note: '' }),
    ).rejects.toThrow('no longer exists')
  })
})
