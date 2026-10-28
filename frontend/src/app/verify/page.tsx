import { Suspense } from 'react'

import VerifyClient from './verify-client'

// useSearchParams needs a Suspense boundary so the rest of the route can prerender.
export default function VerifyPage() {
  return (
    <Suspense fallback={<main className="desk inner-desk" aria-busy="true" />}>
      <VerifyClient />
    </Suspense>
  )
}
