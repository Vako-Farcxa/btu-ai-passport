import type { Metadata } from 'next'
import { Noto_Sans_Georgian, Noto_Serif_Georgian } from 'next/font/google'
import type { ReactNode } from 'react'

import { LocaleLang } from '@/components/locale-lang'

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

export const metadata: Metadata = {
  title: 'BTU AI Skills Digital Passport',
  description: 'Verify a BTU AI skills passport.',
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
