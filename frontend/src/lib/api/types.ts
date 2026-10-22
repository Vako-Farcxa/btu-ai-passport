import { z } from 'zod'

export const skillSchema = z.object({
  skill: z.string(),
  badge: z.string(),
  awarded_on: z.string().nullable(),
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
  z.object({ outcome: z.literal('outdated'), ...foundFields }),
  z.object({ outcome: z.literal('not_found') }),
  z.object({ outcome: z.literal('error') }),
])

export type Skill = z.infer<typeof skillSchema>
export type VerifyResult = z.infer<typeof verifyResultSchema>

export class VerifyInputError extends Error {
  constructor() {
    super('code_required')
    this.name = 'VerifyInputError'
  }
}
