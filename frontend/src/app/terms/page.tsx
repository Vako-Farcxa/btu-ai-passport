import type { Metadata } from 'next'

import { InfoPage } from '@/components/info-page'

export const metadata: Metadata = {
  title: 'Terms of use',
  description:
    'Terms of use for the BTU AI Skills Digital Passport student hackathon demo.',
}

export default function TermsPage() {
  return <InfoPage page="terms" />
}
