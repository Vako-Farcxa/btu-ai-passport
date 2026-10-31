import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import { ConfirmProvider, useConfirm } from './confirm-dialog'

afterEach(cleanup)

function Harness({ destructive = true }: { destructive?: boolean }) {
  const confirm = useConfirm()
  const [answer, setAnswer] = useState('none')
  return (
    <>
      <button
        onClick={async () =>
          setAnswer(
            (await confirm({
              title: 'Delete it?',
              description: 'This cannot be undone.',
              confirmLabel: 'Delete',
              destructive,
            }))
              ? 'yes'
              : 'no',
          )
        }
      >
        Open
      </button>
      <p data-testid="answer">{answer}</p>
    </>
  )
}

const setup = (destructive = true) =>
  render(
    <ConfirmProvider>
      <Harness destructive={destructive} />
    </ConfirmProvider>,
  )

const open = async () => {
  fireEvent.click(screen.getByRole('button', { name: 'Open' }))
  return screen.findByRole('alertdialog')
}
const closed = () =>
  waitFor(() =>
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument(),
  )

describe('ConfirmProvider', () => {
  it('has an accessible name and description', async () => {
    setup()
    const dialog = await open()
    expect(dialog).toHaveAccessibleName('Delete it?')
    expect(dialog).toHaveAccessibleDescription('This cannot be undone.')
  })

  it('resolves true on the confirm button', async () => {
    setup()
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await closed()
    expect(screen.getByTestId('answer')).toHaveTextContent('yes')
  })

  it('resolves false on Cancel', async () => {
    setup()
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await closed()
    expect(screen.getByTestId('answer')).toHaveTextContent('no')
  })

  it('resolves false on Escape', async () => {
    setup()
    await open()
    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: 'Escape',
    })
    await closed()
    expect(screen.getByTestId('answer')).toHaveTextContent('no')
  })

  it('starts on Cancel so Enter never confirms by accident', async () => {
    setup()
    await open()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus(),
    )
  })

  it('makes the page behind it unreachable while open', async () => {
    setup()
    await open()
    expect(screen.queryByRole('button', { name: 'Open' })).toBeNull()
  })

  it('styles the confirm button as danger only when asked', async () => {
    setup(true)
    await open()
    expect(screen.getByRole('button', { name: 'Delete' })).toHaveAttribute(
      'data-variant',
      'danger',
    )
    cleanup()
    setup(false)
    await open()
    expect(screen.getByRole('button', { name: 'Delete' })).toHaveAttribute(
      'data-variant',
      'default',
    )
  })

  it('returns focus to the button that opened it', async () => {
    setup()
    const trigger = screen.getByRole('button', { name: 'Open' })
    trigger.focus()
    fireEvent.click(trigger)
    await screen.findByRole('alertdialog')
    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: 'Escape',
    })
    await closed()
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('throws a clear error when used without the provider', () => {
    const spy = () => render(<Harness />)
    expect(spy).toThrow('useConfirm needs a <ConfirmProvider>')
  })
})
