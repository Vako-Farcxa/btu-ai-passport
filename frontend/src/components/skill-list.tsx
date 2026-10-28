'use client'

import { ChevronDown } from 'lucide-react'
import Image from 'next/image'
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'

import { useSkillMotion } from '@/components/motion'
import { messages, type Locale } from '@/i18n/messages'
import type { Skill } from '@/lib/api/types'
import { formatIssuedDate, presentSkills } from '@/lib/api/verify'
import { badgeCodeFor, stampFor } from '@/lib/stamps'

export function SkillList({
  skills,
  locale,
}: {
  skills: Skill[]
  locale: Locale
}) {
  const copy = messages[locale]
  const ref = useRef<HTMLDivElement>(null)
  const shown = presentSkills(skills, locale)
  useSkillMotion(ref)

  return (
    <div ref={ref} className="skill-block">
      <div className="skills-title">
        <span>{copy.skills}</span>
        <b>{String(shown.length).padStart(2, '0')}</b>
      </div>
      <div className="skills-list">
        {shown.map((skill, index) => (
          <SkillRow
            key={`${index}-${skill.skill}-${skill.badge}-${skill.awarded_on ?? 'none'}`}
            skill={skill}
            index={index}
            locale={locale}
          />
        ))}
      </div>
    </div>
  )
}

function SkillRow({
  skill,
  index,
  locale,
}: {
  skill: Skill
  index: number
  locale: Locale
}) {
  const copy = messages[locale]
  const [open, setOpen] = useState(false)
  const descriptionId = useId()

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape' && open) {
      event.stopPropagation()
      setOpen(false)
    }
  }

  return (
    <div className="skill-row">
      <span className="skill-number">{String(index + 1).padStart(2, '0')}</span>
      <div className="skill-copy" onKeyDown={onKeyDown}>
        {skill.description ? (
          <>
            <b>
              <button
                type="button"
                className="skill-name"
                aria-expanded={open}
                aria-controls={descriptionId}
                onClick={() => setOpen(!open)}
              >
                {skill.skill}
                <ChevronDown
                  aria-hidden="true"
                  size={14}
                  className={open ? 'skill-chevron open' : 'skill-chevron'}
                />
              </button>
            </b>
            <span className="skill-badge">{skill.badge}</span>
            <span
              id={descriptionId}
              className="skill-description"
              hidden={!open}
            >
              {skill.description}
            </span>
          </>
        ) : (
          <>
            <b>{skill.skill}</b>
            <span className="skill-badge">{skill.badge}</span>
          </>
        )}
      </div>
      <time dateTime={skill.awarded_on ?? undefined}>
        {skill.awarded_on
          ? (formatIssuedDate(skill.awarded_on, locale) ?? skill.awarded_on)
          : copy.dateUnavailable}
      </time>
      <BadgeStamp badge={skill.badge} locale={locale} />
    </div>
  )
}

/**
 * The badge stamp as a button with a tooltip naming the badge level.
 * The tooltip text is always in the page, so screen readers get it through
 * aria-describedby. Hover and keyboard focus show it, a tap pins it, Esc closes it.
 */
function BadgeStamp({ badge, locale }: { badge: string; locale: Locale }) {
  const code = badgeCodeFor(badge)
  const stamp = stampFor(badge)
  const tipId = useId()
  const [hover, setHover] = useState(false)
  const [focused, setFocused] = useState(false)
  const [pinned, setPinned] = useState(false)
  const wrap = useRef<HTMLSpanElement>(null)
  const shown = hover || focused || pinned

  useEffect(() => {
    if (!pinned) return
    function onOutside(event: PointerEvent) {
      if (!wrap.current?.contains(event.target as Node)) setPinned(false)
    }
    document.addEventListener('pointerdown', onOutside)
    return () => document.removeEventListener('pointerdown', onOutside)
  }, [pinned])

  if (code === null || stamp === null) return null
  const level = messages[locale].badgeLevels[code]

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== 'Escape' || !shown) return
    event.stopPropagation()
    setHover(false)
    setFocused(false)
    setPinned(false)
  }

  return (
    <span
      ref={wrap}
      className="stamp-wrap"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <button
        type="button"
        className="stamp-button"
        aria-label={level.title}
        aria-describedby={tipId}
        onClick={() => setPinned(!pinned)}
        onFocus={(event) => setFocused(focusIsVisible(event.currentTarget))}
        onBlur={() => {
          setFocused(false)
          setPinned(false)
        }}
        onKeyDown={onKeyDown}
      >
        <Image
          className="badge-stamp"
          src={stamp.src}
          alt=""
          width={stamp.width}
          height={stamp.height}
          unoptimized
        />
      </button>
      <span
        id={tipId}
        role="tooltip"
        className={shown ? 'stamp-tip open' : 'stamp-tip'}
      >
        <b>{level.title}</b>
        {level.text}
      </span>
    </span>
  )
}

// Only keyboard focus opens the tooltip. A mouse or touch click is handled by onClick.
function focusIsVisible(element: HTMLElement): boolean {
  try {
    return element.matches(':focus-visible')
  } catch {
    return true
  }
}
