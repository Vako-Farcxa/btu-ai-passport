import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import type { ReactNode } from 'react'
import { preconnect } from 'react-dom'

import { LocaleLang } from '@/components/locale-lang'
import { LocaleProvider } from '@/components/locale-provider'
import { SkipLink } from '@/components/skip-link'

import { isLocale, LOCALES } from '@/i18n/negotiate'
import { SITE_NAME, SITE_URL } from '@/lib/site'

import '../globals.css'
import { sans, serif } from '../fonts'

const description =
  'Verify a BTU AI skills passport. A student hackathon project, not an official BTU service.'

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: SITE_NAME, template: `%s | ${SITE_NAME}` },
  description,
  applicationName: SITE_NAME,
  openGraph: {
    type: 'website',
    siteName: SITE_NAME,
    title: SITE_NAME,
    description,
    locale: 'en_US',
    alternateLocale: ['ka_GE'],
  },
  twitter: {
    card: 'summary_large_image',
    title: SITE_NAME,
    description,
  },
}

/** The origin of a configured URL, or null when it is missing or not a URL. */
function originOf(value: string | undefined): string | null {
  if (!value?.trim()) return null
  try {
    return new URL(value.trim()).origin
  } catch {
    return null
  }
}

// Two prerendered copies of every page, one per language. `proxy.ts` picks the copy for each
// request (saved choice, else Accept-Language) and rewrites to it, so the address bar never
// shows the language and the static shell stays cacheable.
export function generateStaticParams() {
  return LOCALES.map((lang) => ({ lang }))
}

export default async function RootLayout({
  children,
  params,
}: {
  children: ReactNode
  params: Promise<{ lang: string }>
}) {
  const { lang } = await params
  if (!isLocale(lang)) notFound()
  // Open the connections to the API and to sign-in while the page is still loading, so the
  // first data request of a passport or admin page does not start with DNS and TLS.
  for (const origin of [
    originOf(process.env.NEXT_PUBLIC_API_URL),
    originOf(process.env.NEXT_PUBLIC_SUPABASE_URL),
  ]) {
    if (origin) preconnect(origin, { crossOrigin: 'anonymous' })
  }
  return (
    <html
      lang={lang}
      className={`${sans.variable} ${serif.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <LocaleProvider locale={lang}>
          <LocaleLang />
          <SkipLink />
          {children}
        </LocaleProvider>
      </body>
    </html>
  )
}
