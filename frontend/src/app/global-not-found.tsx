import type { Metadata } from 'next'

import { LocaleLang } from '@/components/locale-lang'
import { StatusPage } from '@/components/status-page'
import { SITE_NAME } from '@/lib/site'

import { sans, serif } from './fonts'
import './globals.css'

export const metadata: Metadata = {
  title: `Page not found | ${SITE_NAME}`,
  robots: { index: false },
}

// The 404 for an address that matches no page. It brings its own shell because no layout
// runs for it. The text starts in English and follows the saved language once the browser
// has loaded, which is fine for a page nobody links to.
export default function GlobalNotFound() {
  return (
    <html
      lang="en"
      className={`${sans.variable} ${serif.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <LocaleLang />
        <StatusPage kind="not_found" />
      </body>
    </html>
  )
}
