import type { BadgeCode } from '@/i18n/messages'

export type StampArt = {
  src: string
  width: number
  height: number
}

const STAMPS: Record<BadgeCode, StampArt> = {
  'BDG-AI-001': { src: '/stamps/BDG-AI-001.png', width: 328, height: 284 },
  'BDG-AI-002': { src: '/stamps/BDG-AI-002.png', width: 656, height: 211 },
  'BDG-AI-003': { src: '/stamps/BDG-AI-003.png', width: 304, height: 304 },
}

/** The official badge code, or null for any other badge text. */
export function badgeCodeFor(badge: string): BadgeCode | null {
  if (
    badge === 'BDG-AI-001' ||
    badge === 'BDG-AI-002' ||
    badge === 'BDG-AI-003'
  ) {
    return badge
  }
  return null
}

export function stampFor(badge: string): StampArt | null {
  const code = badgeCodeFor(badge)
  return code === null ? null : STAMPS[code]
}
