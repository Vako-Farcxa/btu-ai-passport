import type { NextConfig } from 'next'

import { assertProductionApiUrl } from './src/lib/build-env'

// Fail the build, not the live site, when the API address is missing or not https.
assertProductionApiUrl(process.env)

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
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
