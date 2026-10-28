import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SkillList } from '@/components/skill-list'
import { messages } from '@/i18n/messages'
import type { Skill } from '@/lib/api/types'

vi.mock('@/components/motion', () => ({ useSkillMotion: () => undefined }))

afterEach(cleanup)

const skills: Skill[] = [
  {
    skill: 'Machine Learning',
    badge: 'BDG-AI-002',
    awarded_on: '2025-06-01',
    description: 'Choose a model the decision can survive.',
  },
  { skill: 'Python', badge: 'Foundation', awarded_on: null, description: '' },
]

describe('skill descriptions', () => {
  it('keeps the list compact and opens a description from the skill name', () => {
    render(<SkillList skills={skills} locale="en" />)
    const name = screen.getByRole('button', { name: 'Machine Learning' })
    const text = screen.getByText('Choose a model the decision can survive.')
    expect(name).toHaveAttribute('aria-expanded', 'false')
    expect(text).not.toBeVisible()
    expect(name.getAttribute('aria-controls')).toBe(text.id)

    fireEvent.click(name)
    expect(name).toHaveAttribute('aria-expanded', 'true')
    expect(text).toBeVisible()

    fireEvent.click(name)
    expect(text).not.toBeVisible()
  })

  it('closes the description with Escape', () => {
    render(<SkillList skills={skills} locale="en" />)
    const name = screen.getByRole('button', { name: 'Machine Learning' })
    fireEvent.click(name)
    fireEvent.keyDown(name, { key: 'Escape' })
    expect(name).toHaveAttribute('aria-expanded', 'false')
  })

  it('has no disclosure for a skill without a description', () => {
    render(<SkillList skills={skills} locale="en" />)
    expect(screen.queryByRole('button', { name: 'Python' })).toBeNull()
    expect(screen.getByText('Python')).toBeVisible()
  })
})

describe('badge level tooltip', () => {
  function stamp() {
    return screen.getByRole('button', {
      name: messages.en.badgeLevels['BDG-AI-002'].title,
    })
  }

  it('is always in the page and linked to the stamp for screen readers', () => {
    render(<SkillList skills={skills} locale="en" />)
    const tip = screen.getByRole('tooltip')
    expect(stamp().getAttribute('aria-describedby')).toBe(tip.id)
    expect(tip).toHaveTextContent(
      'Awarded for applying an AI skill in practice.',
    )
    expect(tip).not.toHaveClass('open')
  })

  it('opens on hover, pins on tap, and closes with Escape', () => {
    render(<SkillList skills={skills} locale="en" />)
    const tip = screen.getByRole('tooltip')

    fireEvent.mouseEnter(stamp().parentElement as HTMLElement)
    expect(tip).toHaveClass('open')
    fireEvent.mouseLeave(stamp().parentElement as HTMLElement)
    expect(tip).not.toHaveClass('open')

    fireEvent.click(stamp())
    expect(tip).toHaveClass('open')
    fireEvent.keyDown(stamp(), { key: 'Escape' })
    expect(tip).not.toHaveClass('open')
  })

  it('closes a pinned tooltip when tapping elsewhere', () => {
    render(<SkillList skills={skills} locale="en" />)
    fireEvent.click(stamp())
    expect(screen.getByRole('tooltip')).toHaveClass('open')
    fireEvent.pointerDown(document.body)
    expect(screen.getByRole('tooltip')).not.toHaveClass('open')
  })

  it('shows nothing for badges that are not official codes', () => {
    render(<SkillList skills={skills.slice(1)} locale="en" />)
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('explains each level in Georgian', () => {
    render(<SkillList skills={skills} locale="ka" />)
    const level = messages.ka.badgeLevels['BDG-AI-002']
    expect(screen.getByRole('button', { name: level.title })).toBeTruthy()
    expect(screen.getByRole('tooltip')).toHaveTextContent(level.text)
  })
})
