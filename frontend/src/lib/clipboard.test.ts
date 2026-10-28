import { describe, expect, it, vi } from 'vitest'

import { copyText } from '@/lib/clipboard'

describe('copyText', () => {
  it('writes the text and reports success', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    await expect(copyText('A1B2-C3D4-E5F6-G7H8', { writeText })).resolves.toBe(
      true,
    )
    expect(writeText).toHaveBeenCalledWith('A1B2-C3D4-E5F6-G7H8')
  })

  it('reports failure when the browser refuses', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'))
    await expect(copyText('code', { writeText })).resolves.toBe(false)
  })

  it('reports failure when there is no clipboard', async () => {
    await expect(copyText('code', undefined)).resolves.toBe(false)
  })
})
