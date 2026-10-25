'use client'

import gsap from 'gsap'

export function entrance(element: HTMLElement): void {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reduced) return
  gsap.from(element, {
    opacity: 0,
    y: 12,
    duration: 0.4,
    ease: 'power2.out',
  })
}
