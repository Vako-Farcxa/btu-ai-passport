import type { Metadata } from 'next'
import type { ReactNode } from 'react'

export const metadata: Metadata = {
  title: 'My passport',
  description: 'Your BTU AI skills passport versions, PDFs and share links.',
  robots: { index: false, follow: false },
}

export default function PassportLayout({ children }: { children: ReactNode }) {
  return children
}
