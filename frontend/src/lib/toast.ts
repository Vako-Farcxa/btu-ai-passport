import { Toast } from '@base-ui/react/toast'

/**
 * One shared toast manager. The Toaster component renders what is added here, so any
 * code (handlers, helpers) can show a toast without a hook. Nothing is shown until a
 * Toaster is mounted.
 */
export const toastManager = Toast.createToastManager()

/** Errors stay a little longer and are announced urgently to screen readers. */
const ERROR_TIMEOUT_MS = 8000
const DEFAULT_TIMEOUT_MS = 5000

function show(
  type: 'success' | 'warning' | 'error' | 'info',
  title: string,
  description?: string,
) {
  return toastManager.add({
    type,
    title,
    description,
    priority: type === 'error' ? 'high' : 'low',
    timeout: type === 'error' ? ERROR_TIMEOUT_MS : DEFAULT_TIMEOUT_MS,
  })
}

export const notify = {
  success: (title: string, description?: string) =>
    show('success', title, description),
  info: (title: string, description?: string) =>
    show('info', title, description),
  warning: (title: string, description?: string) =>
    show('warning', title, description),
  error: (title: string, description?: string) =>
    show('error', title, description),
}
