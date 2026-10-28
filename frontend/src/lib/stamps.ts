const STAMPS = {
  'BDG-AI-001': { src: '/stamps/BDG-AI-001.png', width: 328, height: 284 },
  'BDG-AI-002': { src: '/stamps/BDG-AI-002.png', width: 656, height: 211 },
  'BDG-AI-003': { src: '/stamps/BDG-AI-003.png', width: 304, height: 304 },
} as const

export type StampArt = {
  src: string
  width: number
  height: number
}

export function stampFor(badge: string): StampArt | null {
  if (
    badge === 'BDG-AI-001' ||
    badge === 'BDG-AI-002' ||
    badge === 'BDG-AI-003'
  ) {
    return STAMPS[badge]
  }
  return null
}
