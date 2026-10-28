import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AddStudentDialog } from '@/components/admin/add-student-dialog'
import * as api from '@/lib/api/admin'

vi.mock('@/lib/api/admin', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api/admin')>('@/lib/api/admin')
  return {
    ...actual,
    fetchAdminSkills: vi.fn(),
    awardAdminSkill: vi.fn(),
  }
})

const skill = {
  id: 'SKL-001',
  name: 'Prompting',
  name_ka: null,
  category: 'AI Skill',
  badge: 'PRM',
  description: '',
  source: 'sheet',
}

function fill(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

describe('AddStudentDialog', () => {
  afterEach(cleanup)

  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(api.fetchAdminSkills).mockResolvedValue([skill] as never)
  })

  it('asks for the student fields and a required skill', async () => {
    render(<AddStudentDialog onClose={() => {}} />)
    expect(await screen.findByLabelText(/first name/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/last name/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/btu email/i)).toBeInTheDocument()
    // IDs are assigned by the system, never typed.
    expect(screen.queryByLabelText(/student id/i)).toBeNull()
    expect(screen.queryByLabelText(/passport id/i)).toBeNull()
    expect(screen.queryByLabelText(/skill id/i)).toBeNull()
    expect(screen.getByText(/leave empty to use today/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/program/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/education level/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/skill \*/i)).toBeInTheDocument()
    expect(screen.getByText(/a skill is required/i)).toBeInTheDocument()
  })

  it('does not submit without a skill', async () => {
    render(<AddStudentDialog onClose={() => {}} />)
    await screen.findByLabelText(/first name/i)
    fill(/first name/i, 'Nino')
    fill(/last name/i, 'Beridze')
    fill(/btu email/i, 'nino@btu.edu.ge')
    fireEvent.click(screen.getByRole('button', { name: 'Add student' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      /choose a skill/i,
    )
    expect(api.awardAdminSkill).not.toHaveBeenCalled()
  })

  it('writes through the awards flow with the student details', async () => {
    const onDone = vi.fn()
    vi.mocked(api.awardAdminSkill).mockResolvedValue({
      sync_result: {
        status: 'completed',
        rows_read: 1,
        versions_created: 1,
        error: null,
      },
      rows: [
        {
          email: 'nino@btu.edu.ge',
          status: 'synced',
          passport_id: 'BTU-ABC',
          version: '1',
          error: '',
        },
      ],
    } as never)
    render(<AddStudentDialog onClose={() => {}} onDone={onDone} />)
    await screen.findByLabelText(/first name/i)
    fill(/first name/i, 'Nino')
    fill(/last name/i, 'Beridze')
    fill(/btu email/i, 'Nino@btu.edu.ge')
    fill(/education level/i, "Bachelor's")
    fill(/program/i, 'Digital Marketing')
    await waitFor(() =>
      expect(
        screen.getByRole('option', { name: /Prompting/ }),
      ).toBeInTheDocument(),
    )
    fill(/skill \*/i, 'SKL-001')
    fireEvent.click(screen.getByRole('button', { name: 'Add student' }))

    await waitFor(() => expect(api.awardAdminSkill).toHaveBeenCalledTimes(1))
    expect(api.awardAdminSkill).toHaveBeenCalledWith(
      expect.objectContaining({
        skill_id: 'SKL-001',
        students: [
          {
            email: 'nino@btu.edu.ge',
            first_name: 'Nino',
            last_name: 'Beridze',
            program: 'Digital Marketing',
            education_level: "Bachelor's",
          },
        ],
      }),
    )
    expect(await screen.findByText(/BTU-ABC/)).toBeInTheDocument()
    expect(onDone).toHaveBeenCalled()
  })

  it('offers programs for the chosen level only', async () => {
    render(<AddStudentDialog onClose={() => {}} />)
    await screen.findByLabelText(/first name/i)
    expect(screen.getByLabelText(/program/i)).toBeDisabled()
    fill(/education level/i, "Master's")
    expect(
      screen.getByRole('option', {
        name: 'International Security and Technologies',
      }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('option', { name: 'Psychology in the Digital World' }),
    ).toBeNull()
    fill(/program/i, 'Digital Marketing')
    fill(/education level/i, "Bachelor's")
    expect((screen.getByLabelText(/program/i) as HTMLSelectElement).value).toBe(
      '',
    )
  })

  it('shows inline errors for a fake student and sends nothing', async () => {
    render(<AddStudentDialog onClose={() => {}} />)
    await screen.findByLabelText(/first name/i)
    fill(/first name/i, '1')
    fill(/last name/i, '1')
    fill(/btu email/i, '111@btu.edu.ge')
    fireEvent.click(screen.getByRole('button', { name: 'Add student' }))
    const alerts = await screen.findAllByRole('alert')
    const text = alerts.map((a) => a.textContent).join(' | ')
    expect(text).toMatch(/First name/)
    expect(text).toMatch(/Last name/)
    expect(text).toMatch(/only digits/)
    expect(screen.getByLabelText(/first name/i)).toHaveAttribute(
      'aria-invalid',
      'true',
    )
    expect(api.awardAdminSkill).not.toHaveBeenCalled()
  })

  it('clears a field error when the admin edits that field', async () => {
    render(<AddStudentDialog onClose={() => {}} />)
    await screen.findByLabelText(/first name/i)
    fireEvent.click(screen.getByRole('button', { name: 'Add student' }))
    expect(await screen.findAllByRole('alert')).not.toHaveLength(0)
    fill(/first name/i, 'Nino')
    expect(screen.getByLabelText(/first name/i)).toHaveAttribute(
      'aria-invalid',
      'false',
    )
  })

  it('closes on Escape', async () => {
    const onClose = vi.fn()
    render(<AddStudentDialog onClose={onClose} />)
    await screen.findByLabelText(/first name/i)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})
