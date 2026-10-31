import type { NextConfig } from 'next'

import { assertProductionApiUrl } from './src/lib/build-env'
import { securityHeaders } from './src/lib/security-headers'

// Fail the build, not the live site, when the API address is missing or not https.
assertProductionApiUrl(process.env)

const nextConfig: NextConfig = {
  // No "X-Powered-By: Next.js" header: it only tells scanners what to aim at.
  poweredByHeader: false,
  /* config options here */
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders(process.env) }]
  },
  cacheComponents: true,
  partialPrefetching: true,
  // The root layout sits under the `[lang]` segment, so Next.js cannot build its own 404 for
  // an unknown address from it. `app/global-not-found.tsx` is that page instead.
  experimental: { globalNotFound: true },
  turbopack: {
    rules: {
      '*.css': {
        loaders: ['@tailwindcss/turbopack'],
        as: '*.css',
      },
    },
  },
}

export default nextConfig
