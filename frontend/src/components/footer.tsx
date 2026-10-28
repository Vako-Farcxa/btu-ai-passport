import Link from 'next/link'

import { messages, type Locale } from '@/i18n/messages'

export function Footer({ locale }: { locale: Locale }) {
  const copy = messages[locale]

  return (
    <footer className="site-footer">
      <div className="site-footer-notices">
        <p className="site-footer-notice testnet">
          <span className="notice-glyph">✦</span>
          {copy.footerTestnetNotice}
        </p>
        <p className="site-footer-notice disclaimer">{copy.footerDisclaimer}</p>
      </div>
      <div className="site-footer-bar">
        <span className="site-footer-copy">
          <span className="footer-monogram">BTU</span> ·{' '}
          {locale === 'en'
            ? copy.universityName.toUpperCase()
            : copy.universityName}{' '}
          · {new Date().getFullYear()}
        </span>
        <nav className="site-footer-nav" aria-label="Footer">
          <Link href="/about">{copy.navAbout}</Link>
          <Link href="/how-it-works">{copy.navHowItWorks}</Link>
          <Link href="/privacy">{copy.navPrivacy}</Link>
        </nav>
      </div>
    </footer>
  )
}
