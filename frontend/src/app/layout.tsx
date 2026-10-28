import type { Metadata } from 'next'
import { Noto_Sans_Georgian, Noto_Serif_Georgian } from 'next/font/google'
import type { ReactNode } from 'react'

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

export default function RootLayout({ children }: { children: ReactNode }) {
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
