'use client'

import { LocaleLang } from '@/components/locale-lang'
import { StatusPage } from '@/components/status-page'

import './globals.css'

// Replaces the root layout when the layout itself fails, so it brings its own shell.
export default function GlobalError({ reset }: { reset: () => void }) {
  return (
    <html lang="en">
      <body>
        <LocaleLang />
        <StatusPage kind="error" onRetry={reset} />
      </body>
    </html>
  )
}
