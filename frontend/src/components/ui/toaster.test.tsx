import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { notify, toastManager } from '@/lib/toast'

import { Toaster } from './toaster'

afterEach(() => {
  act(() => toastManager.close())
  cleanup()
})

const toasts = () => screen.findAllByTestId('toast')

describe('Toaster', () => {
  it('shows a success toast with a title and details', async () => {
    render(<Toaster />)
    act(() => {
      notify.success('Saved', 'Everything is up to date.')
    })
    const [toast] = await toasts()
    expect(toast).toHaveAttribute('data-type', 'success')
    expect(toast).toHaveTextContent('Saved')
    expect(toast).toHaveTextContent('Everything is up to date.')
  })

  it('marks errors as urgent and other kinds as polite', async () => {
    render(<Toaster />)
    act(() => {
      notify.error('Broke')
      notify.info('FYI')
    })
    await waitFor(async () => expect(await toasts()).toHaveLength(2))
    const all = await toasts()
    const byTitle = (title: string) =>
      all.find((el) => el.textContent?.includes(title))
    expect(byTitle('Broke')).toHaveAttribute('role', 'alertdialog')
    expect(byTitle('FYI')).toHaveAttribute('role', 'dialog')
  })

  it('has a labelled notifications region and a dismiss button', async () => {
    render(<Toaster />)
    act(() => {
      notify.warning('Careful')
    })
    await toasts()
    expect(
      screen.getByRole('region', { name: 'Notifications' }),
    ).toBeInTheDocument()
    act(() => {
      // Base UI hides the close button from assistive tech until the toast region is
      // focused (F6) or hovered, so it is looked up by label here.
      screen.getByLabelText('Dismiss notification').click()
    })
    await waitFor(() =>
      expect(screen.queryByTestId('toast')).not.toBeInTheDocument(),
    )
  })

  it('uses no dashes in its own labels', async () => {
    render(<Toaster />)
    act(() => {
      notify.info('Hello')
    })
    const [toast] = await toasts()
    expect(toast?.textContent).not.toMatch(/\u2014|\u2013/)
  })
})
