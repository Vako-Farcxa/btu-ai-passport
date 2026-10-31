'use client'

import { AlertDialog } from '@base-ui/react/alert-dialog'
import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { Button } from '@/components/ui/button'

export type ConfirmOptions = {
  title: string
  description: ReactNode
  /** The button that goes ahead, for example "Archive student". */
  confirmLabel: string
  cancelLabel?: string
  /** Styles the confirm button as a danger action. Use for anything that is hard to undo. */
  destructive?: boolean
}

type Confirm = (options: ConfirmOptions) => Promise<boolean>

const ConfirmContext = createContext<Confirm | null>(null)

/**
 * Replaces window.confirm. `await confirm({...})` resolves true only when the admin
 * presses the confirm button. Escape, Cancel and clicking outside all resolve false.
 * Focus starts on Cancel, is trapped inside the dialog and returns to the button that
 * opened it.
 */
export function useConfirm(): Confirm {
  const confirm = useContext(ConfirmContext)
  if (!confirm) throw new Error('useConfirm needs a <ConfirmProvider>')
  return confirm
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [options, setOptions] = useState<ConfirmOptions | null>(null)
  const [open, setOpen] = useState(false)
  const resolver = useRef<((value: boolean) => void) | null>(null)

  const confirm = useCallback<Confirm>((next) => {
    // A second request while one is open cancels the first, so no promise hangs.
    resolver.current?.(false)
    setOptions(next)
    setOpen(true)
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve
    })
  }, [])

  const settle = useCallback((value: boolean) => {
    resolver.current?.(value)
    resolver.current = null
    setOpen(false)
  }, [])

  const cancelRef = useRef<HTMLButtonElement>(null)

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <AlertDialog.Root
        open={open}
        onOpenChange={(next) => {
          if (!next) settle(false)
        }}
      >
        <AlertDialog.Portal>
          <AlertDialog.Backdrop className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs transition-opacity duration-150 data-ending-style:opacity-0 data-starting-style:opacity-0" />
          <AlertDialog.Popup
            initialFocus={cancelRef}
            className="fixed top-1/2 left-1/2 z-50 flex w-md max-w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col gap-5 rounded-2xl border border-slate-200 bg-white p-6 text-slate-900 shadow-xl transition-[scale,opacity] duration-150 data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0"
          >
            <div className="space-y-2">
              <AlertDialog.Title className="text-lg font-bold">
                {options?.title}
              </AlertDialog.Title>
              <AlertDialog.Description className="text-sm text-slate-600">
                {options?.description}
              </AlertDialog.Description>
            </div>
            <div className="flex justify-end gap-3">
              <Button
                ref={cancelRef}
                variant="outline"
                size="lg"
                onClick={() => settle(false)}
              >
                {options?.cancelLabel ?? 'Cancel'}
              </Button>
              <Button
                variant={options?.destructive ? 'danger' : 'default'}
                size="lg"
                data-variant={options?.destructive ? 'danger' : 'default'}
                onClick={() => settle(true)}
              >
                {options?.confirmLabel}
              </Button>
            </div>
          </AlertDialog.Popup>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </ConfirmContext.Provider>
  )
}
