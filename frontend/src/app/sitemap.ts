import type { MetadataRoute } from 'next'

import { SITE_URL } from '@/lib/site'

const PATHS = ['/', '/verify', '/about', '/privacy', '/terms']

export default function sitemap(): MetadataRoute.Sitemap {
  return PATHS.map((path) => ({ url: `${SITE_URL}${path}` }))
}
