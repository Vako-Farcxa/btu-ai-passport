import type { Locale } from '@/i18n/messages'
import { trust } from '@/i18n/trust'

/** Says anchoring is on a test network. Shown wherever a transaction is. */
export function TestnetNote({ locale }: { locale: Locale }) {
  return (
    <p className="testnet-note" data-testid="testnet-note">
      {trust[locale].testnetNote}
    </p>
  )
}
