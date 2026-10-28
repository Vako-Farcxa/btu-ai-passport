'use client'

import Link from 'next/link'

import { OpenBook } from '@/components/book'
import { useLocale } from '@/i18n/use-locale'
import { trust, type InfoPageId } from '@/i18n/trust'
import { CONTACT_EMAIL } from '@/lib/contact'

const FOLIOS: Record<InfoPageId, string> = {
  about: '04',
  privacy: '05',
  terms: '06',
}

export function InfoPage({ page }: { page: InfoPageId }) {
  const [locale, setLocale] = useLocale()
  const copy = trust[locale]
  const content = copy.pages[page]
  const removal = CONTACT_EMAIL
    ? copy.removalWithEmail.replace('{email}', CONTACT_EMAIL)
    : copy.removalWithoutEmail

  return (
    <OpenBook locale={locale} onLocale={setLocale} folio={FOLIOS[page]}>
      <article className="info-page" data-testid={`info-${page}`}>
        <Link className="back-link" href="/">
          ← {copy.backHome}
        </Link>
        <span className="eyebrow">BTU · 2026</span>
        <h1>{content.title}</h1>
        <p className="intro">{content.intro}</p>
        {content.sections.map((section) => (
          <section key={section.heading} className="info-section">
            <h2>{section.heading}</h2>
            {section.list ? (
              <ul>
                {section.body.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              section.body.map((paragraph) => (
                <p key={paragraph}>
                  {paragraph === '{removal}' ? removal : paragraph}
                </p>
              ))
            )}
            {section.link ? (
              <p>
                <a
                  className="info-link"
                  href={section.link.href}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {section.link.label}
                </a>
              </p>
            ) : null}
          </section>
        ))}
      </article>
    </OpenBook>
  )
}
