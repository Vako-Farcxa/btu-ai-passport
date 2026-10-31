import type { Metadata } from 'next'

import { InfoPage } from '@/components/info-page'

export const metadata: Metadata = {
  title: 'About',
  description:
    'What a BTU AI Skills Digital Passport is, how verification works and what blockchain anchoring proves. A student hackathon project.',
}

export default function AboutPage() {
  return <InfoPage page="about" />
}
