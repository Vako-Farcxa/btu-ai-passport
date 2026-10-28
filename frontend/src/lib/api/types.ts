import { z } from 'zod'

export const skillSchema = z.object({
  skill: z.string(),
  badge: z.string(),
  awarded_on: z.string().nullable(),
  description: z.string().default(''),
})

const foundFields = {
  holder_name: z.string(),
  version: z.number().int().positive(),
  is_latest: z.boolean(),
  skills: z.array(skillSchema),
  tx_url: z.string().url(),
}

export const verifyResultSchema = z.discriminatedUnion('outcome', [
  z.object({ outcome: z.literal('valid'), ...foundFields }),
  z.object({
    outcome: z.literal('outdated'),
    ...foundFields,
    // Added by newer backends. Older ones omit them, so the note is optional.
    latest_version: z.number().int().positive().nullish(),
    latest_issued_at: z.string().nullish(),
  }),
  z.object({ outcome: z.literal('not_found') }),
  z.object({ outcome: z.literal('error') }),
])

export const passportVersionSchema = z.object({
  version: z.number().int().positive(),
  issued_at: z.string(),
  is_current: z.boolean(),
  holder_name: z.string(),
  verification_code: z.string(),
  skills: z.array(skillSchema),
  anchor: z.object({
    status: z.enum(['pending', 'confirmed', 'failed']),
    tx_url: z.string().url().nullable(),
  }),
})

export const passportResponseSchema = z.object({
  passport: z
    .object({
      passport_id: z.string(),
      versions: z.array(passportVersionSchema),
    })
    .nullable(),
})

export type Skill = z.infer<typeof skillSchema>
export type VerifyResult = z.infer<typeof verifyResultSchema>
export type PassportResponse = z.infer<typeof passportResponseSchema>
export type PassportVersion = z.infer<typeof passportVersionSchema>

export class VerifyInputError extends Error {
  constructor() {
    super('code_required')
    this.name = 'VerifyInputError'
  }
}

export class VerifyRateLimitError extends Error {
  constructor() {
    super('rate_limited')
    this.name = 'VerifyRateLimitError'
  }
}
