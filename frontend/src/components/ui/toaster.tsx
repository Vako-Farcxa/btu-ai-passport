'use client'

import { Toast } from '@base-ui/react/toast'
import { cn } from 'cn'
import { CircleAlert, CircleCheck, Info, TriangleAlert, X } from 'lucide-react'

import { toastManager } from '@/lib/toast'

const TONE: Record<string, string> = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  warning: 'border-amber-200 bg-amber-50 text-amber-900',
  error: 'border-rose-200 bg-rose-50 text-rose-900',
  info: 'border-slate-200 bg-white text-slate-900',
}

function ToastIcon({ type }: { type?: string }) {
  const className = 'mt-0.5 size-4 shrink-0'
  if (type === 'success')
    return <CircleCheck aria-hidden="true" className={className} />
  if (type === 'error')
    return <CircleAlert aria-hidden="true" className={className} />
  if (type === 'warning')
    return <TriangleAlert aria-hidden="true" className={className} />
  return <Info aria-hidden="true" className={className} />
}

function ToastList() {
  const { toasts } = Toast.useToastManager()
  return toasts.map((toast) => (
    <Toast.Root
      key={toast.id}
      toast={toast}
      data-testid="toast"
      data-type={toast.type}
      className={cn(
        'pointer-events-auto flex w-full items-start gap-3 rounded-xl border p-3 text-sm shadow-lg outline-none transition-all duration-200 focus-visible:ring-3 focus-visible:ring-ring/50',
        'data-starting-style:translate-y-2 data-starting-style:opacity-0 data-ending-style:opacity-0',
        TONE[toast.type ?? 'info'] ?? TONE.info,
      )}
    >
      <ToastIcon type={toast.type} />
      <Toast.Content className="flex min-w-0 flex-1 flex-col gap-0.5">
        <Toast.Title className="font-semibold" />
        <Toast.Description className="text-xs opacity-90" />
      </Toast.Content>
      <Toast.Close
        aria-label="Dismiss notification"
        className="-m-1 shrink-0 rounded-md p-1 opacity-70 outline-none hover:opacity-100 focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <X aria-hidden="true" className="size-4" />
      </Toast.Close>
    </Toast.Root>
  ))
}

/** Renders toasts added with `notify`. Mount once, near the top of a layout. */
export function Toaster() {
  return (
    <Toast.Provider toastManager={toastManager} limit={4}>
      <Toast.Portal>
        <Toast.Viewport
          aria-label="Notifications"
          className="pointer-events-none fixed inset-x-4 bottom-4 z-[60] flex flex-col gap-2 sm:left-auto sm:right-6 sm:bottom-6 sm:w-96"
        >
          <ToastList />
        </Toast.Viewport>
      </Toast.Portal>
    </Toast.Provider>
  )
}
