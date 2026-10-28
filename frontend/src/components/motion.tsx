'use client'

import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import type { RefObject } from 'react'

if (typeof window !== 'undefined') {
  gsap.registerPlugin(useGSAP)
}

function useMotion(
  scope: RefObject<HTMLElement | null>,
  animate: (root: HTMLElement) => void,
) {
  useGSAP(
    () => {
      const root = scope.current
      if (!root) return
      const motion = gsap.matchMedia()
      motion.add(
        '(prefers-reduced-motion: no-preference)',
        () => {
          animate(root)
        },
        root,
      )
      return () => {
        motion.revert()
      }
    },
    { scope },
  )
}

export function useCoverMotion(scope: RefObject<HTMLElement | null>) {
  useMotion(scope, (root) => {
    const cover = root.querySelector('.book-cover')
    const pages = root.querySelector('.book-pages')
    const ribbon = root.querySelector('.book-ribbon')
    const bar = root.querySelector('.topbar')
    const note = root.querySelector('.landing-note')
    const tl = gsap.timeline({ defaults: { ease: 'power3.out' } })
    if (bar) {
      tl.from(bar, { y: -14, duration: 0.5, clearProps: 'transform' }, 0)
    }
    if (cover) {
      tl.from(
        cover,
        {
          rotationY: -48,
          rotationX: 7,
          transformOrigin: 'left center',
          duration: 1.15,
          clearProps: 'transform',
        },
        0.05,
      )
    }
    if (pages) {
      tl.from(
        pages,
        { y: 12, opacity: 0, duration: 0.55, clearProps: 'opacity,transform' },
        0.35,
      )
    }
    if (ribbon) {
      tl.from(
        ribbon,
        {
          y: -30,
          duration: 0.5,
          ease: 'power2.out',
          clearProps: 'transform',
        },
        0.45,
      )
    }
    if (note) {
      tl.from(note, { y: 8, duration: 0.4, clearProps: 'transform' }, 0.5)
    }
  })
}

export function useOpenBookMotion(scope: RefObject<HTMLElement | null>) {
  useMotion(scope, (root) => {
    const book = root.querySelector('.open-book')
    const bar = root.querySelector('.topbar')
    const seal = root.querySelector('.seal')
    const tl = gsap.timeline({ defaults: { ease: 'power3.out' } })
    if (bar) {
      tl.from(bar, { y: -12, duration: 0.45, clearProps: 'transform' }, 0)
    }
    if (book) {
      tl.from(
        book,
        {
          y: 32,
          rotationX: 5,
          transformOrigin: 'center top',
          duration: 0.9,
          clearProps: 'transform',
        },
        0.05,
      )
    }
    if (seal) {
      tl.from(
        seal,
        {
          scale: 0.7,
          rotation: -18,
          duration: 0.55,
          ease: 'back.out(1.7)',
          clearProps: 'transform',
        },
        0.35,
      )
    }
  })
}

export function useSkillMotion(scope: RefObject<HTMLElement | null>) {
  useMotion(scope, (root) => {
    const rows = root.querySelectorAll('.skill-row')
    const stamps = root.querySelectorAll('.badge-stamp')
    if (rows.length) {
      gsap.from(rows, {
        y: 14,
        duration: 0.45,
        stagger: 0.08,
        delay: 0.05,
        ease: 'power2.out',
        clearProps: 'transform',
      })
    }
    if (stamps.length) {
      gsap.from(stamps, {
        y: -18,
        scale: 1.55,
        rotation: -18,
        opacity: 0,
        duration: 0.36,
        stagger: 0.12,
        delay: 0.16,
        ease: 'back.out(1.8)',
        transformOrigin: 'center',
        clearProps: 'opacity,transform',
      })
    }
  })
}

export function useResultMotion(scope: RefObject<HTMLElement | null>) {
  useMotion(scope, (root) => {
    const icon = root.querySelector('.valid-icon')
    gsap.from(root, {
      y: 22,
      scale: 0.965,
      duration: 0.6,
      ease: 'power3.out',
      transformOrigin: '50% 0%',
      clearProps: 'transform',
    })
    if (icon) {
      gsap.from(icon, {
        scale: 0.45,
        rotation: -16,
        duration: 0.42,
        delay: 0.12,
        ease: 'back.out(2.1)',
        transformOrigin: 'center',
        clearProps: 'transform',
      })
    }
  })
}
