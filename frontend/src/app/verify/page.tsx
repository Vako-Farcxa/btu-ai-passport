import type { Metadata } from 'next'
import { Suspense } from 'react'

import VerifyClient from './verify-client'

export const metadata: Metadata = {
  title: 'Verify a passport',
  description:
    'Check a BTU AI skills passport verification code. Student hackathon demo.',
}

// useSearchParams needs a Suspense boundary so the rest of the route can prerender.
export default function VerifyPage() {
  return (
    <Suspense
      fallback={<main id="main" className="desk inner-desk" aria-busy="true" />}
    >
      <VerifyClient />
    </Suspense>
  )
}
