'use client'

import { StatusPage } from '@/components/status-page'

import './globals.css'

// Replaces the root layout when the layout itself fails, so it brings its own shell.
export default function GlobalError({ reset }: { reset: () => void }) {
  return (
    <html lang="ka">
      <body>
        <StatusPage kind="error" onRetry={reset} />
      </body>
    </html>
  )
}
