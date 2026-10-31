import type { Metadata } from 'next'

import { InfoPage } from '@/components/info-page'

export const metadata: Metadata = {
  title: 'Privacy',
  description:
    'What the BTU AI Skills Digital Passport shows and stores, where it is stored, and who to contact about it.',
}

export default function PrivacyPage() {
  return <InfoPage page="privacy" />
}
