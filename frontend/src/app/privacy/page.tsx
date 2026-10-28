import type { Metadata } from 'next'

import { InfoPage } from '@/components/info-page'

export const metadata: Metadata = {
  title: 'Privacy',
  description:
    'What data the BTU AI Skills Digital Passport demo stores and what a verifier can see.',
}

export default function PrivacyPage() {
  return <InfoPage page="privacy" />
}
