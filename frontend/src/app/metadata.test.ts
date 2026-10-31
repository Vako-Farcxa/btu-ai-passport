import { describe, expect, it, vi } from 'vitest'

import robots from '@/app/robots'
import sitemap from '@/app/sitemap'
import { metadata as root } from '@/app/[lang]/layout'
import { metadata as admin } from '@/app/[lang]/admin/layout'
import { metadata as about } from '@/app/[lang]/about/page'
import { metadata as privacy } from '@/app/[lang]/privacy/page'
import { metadata as terms } from '@/app/[lang]/terms/page'
import { metadata as verify } from '@/app/[lang]/verify/page'

vi.mock('next/font/google', () => {
  const font = () => ({ variable: '' })
  return { Noto_Sans_Georgian: font, Noto_Serif_Georgian: font }
})

describe('page metadata', () => {
  it('sets the base URL, Open Graph and Twitter tags on the root', () => {
    expect(String(root.metadataBase)).toBe(
      'https://btu-ai-passport.vercel.app/',
    )
    expect(root.openGraph).toMatchObject({ type: 'website' })
    expect(root.twitter).toMatchObject({ card: 'summary_large_image' })
  })

  it('gives each public page its own title', () => {
    const titles = [about, privacy, terms, verify].map((m) => m.title)
    expect(new Set(titles).size).toBe(4)
  })

  it('has no em-dash in any title or description', () => {
    for (const meta of [root, admin, about, privacy, terms, verify]) {
      expect(JSON.stringify(meta)).not.toContain('\u2014')
    }
  })

  it('keeps the admin panel out of search', () => {
    expect(admin.robots).toMatchObject({ index: false })
    const rules = robots().rules
    const disallow = Array.isArray(rules) ? rules[0]?.disallow : rules.disallow
    expect(disallow).toContain('/admin')
  })

  it('lists the public pages in the sitemap', () => {
    const urls = sitemap().map((entry) => entry.url)
    expect(urls).toContain('https://btu-ai-passport.vercel.app/about')
    expect(urls).toContain('https://btu-ai-passport.vercel.app/privacy')
    expect(urls.some((url) => url.includes('/admin'))).toBe(false)
  })
})
