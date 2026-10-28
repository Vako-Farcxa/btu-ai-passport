'use client'

import { StatusPage } from '@/components/status-page'

export default function ErrorPage({ reset }: { reset: () => void }) {
  return <StatusPage kind="error" onRetry={reset} />
}
