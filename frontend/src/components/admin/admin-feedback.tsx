'use client'

import type { ReactNode } from 'react'

import { ConfirmProvider } from '@/components/ui/confirm-dialog'
import { Toaster } from '@/components/ui/toaster'

/** Gives every admin page confirm dialogs and toasts, in place of the browser's popups. */
export function AdminFeedback({ children }: { children: ReactNode }) {
  return (
    <ConfirmProvider>
      {children}
      <Toaster />
    </ConfirmProvider>
  )
}
