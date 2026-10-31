import type { Metadata } from 'next'
import { Noto_Sans_Georgian, Noto_Serif_Georgian } from 'next/font/google'
import type { ReactNode } from 'react'
import { preconnect } from 'react-dom'

import { LocaleLang } from '@/components/locale-lang'

import { SITE_NAME, SITE_URL } from '@/lib/site'

import './globals.css'

const sans = Noto_Sans_Georgian({
  subsets: ['latin', 'georgian'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-sans-geo',
  display: 'swap',
})

const serif = Noto_Serif_Georgian({
  subsets: ['latin', 'georgian'],
  weight: ['500', '600', '700'],
  variable: '--font-serif-geo',
  display: 'swap',
})

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

export default function RootLayout({ children }: { children: ReactNode }) {
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
      lang="ka"
      className={`${sans.variable} ${serif.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <LocaleLang />
        {children}
      </body>
    </html>
  )
}
