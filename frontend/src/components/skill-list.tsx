'use client'

import Image from 'next/image'
import { useRef } from 'react'

import { useSkillMotion } from '@/components/motion'
import { messages, type Locale } from '@/i18n/messages'
import type { Skill } from '@/lib/api/types'
import { presentSkills } from '@/lib/api/verify'
import { stampFor } from '@/lib/stamps'

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
        {shown.map((skill, index) => {
          const stamp = stampFor(skill.badge)
          return (
            <div
              className="skill-row"
              key={`${index}-${skill.skill}-${skill.badge}-${skill.awarded_on ?? 'none'}`}
            >
              <span className="skill-number">
                {String(index + 1).padStart(2, '0')}
              </span>
              <div className="skill-copy">
                <b>{skill.skill}</b>
                <span className="skill-badge">{skill.badge}</span>
                {skill.description ? (
                  <span className="skill-description">{skill.description}</span>
                ) : null}
              </div>
              <time dateTime={skill.awarded_on ?? undefined}>
                {skill.awarded_on ?? copy.dateUnavailable}
              </time>
              {stamp ? (
                <Image
                  className="badge-stamp"
                  src={stamp.src}
                  alt=""
                  width={stamp.width}
                  height={stamp.height}
                  unoptimized
                />
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}
