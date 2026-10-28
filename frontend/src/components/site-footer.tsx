'use client'

import Link from 'next/link'

import type { Locale } from '@/i18n/messages'
import { REPO_URL } from '@/lib/site'
import { trust } from '@/i18n/trust'

export function SiteFooter({ locale }: { locale: Locale }) {
  const copy = trust[locale]
  return (
    <footer className="site-footer" lang={locale}>
      <p className="site-footer-project">{copy.projectLine}</p>
      <p className="site-footer-team">
        <span>{copy.teamLabel}:</span> {copy.team}
      </p>
      <nav className="site-footer-links" aria-label={copy.footerLabel}>
        <Link href="/about">{copy.navAbout}</Link>
        <span aria-hidden="true">·</span>
        <Link href="/privacy">{copy.navPrivacy}</Link>
        <span aria-hidden="true">·</span>
        <Link href="/terms">{copy.navTerms}</Link>
        <span aria-hidden="true">·</span>
        <a href={REPO_URL} target="_blank" rel="noopener noreferrer">
          {copy.navGithub}
        </a>
      </nav>
    </footer>
  )
}
