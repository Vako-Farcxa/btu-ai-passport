import type { ReactNode } from 'react'

import { BrandMark, Seal } from '@/components/book'
import { Footer } from '@/components/footer'
import { LocaleSwitcher } from '@/components/locale-switcher'
import type { Locale } from '@/i18n/messages'

export function InfoLayout({
  locale,
  onLocale,
  title,
  subtitle,
  children,
}: {
  locale: Locale
  onLocale: (locale: Locale) => void
  title: string
  subtitle?: string
  children: ReactNode
}) {
  return (
    <div className="min-h-screen flex flex-col bg-[#0f172a] text-slate-100">
      <header className="topbar">
        <BrandMark locale={locale} />
        <LocaleSwitcher locale={locale} onChange={onLocale} />
      </header>

      <main className="flex-1 max-w-3xl w-full mx-auto px-6 py-12">
        <div className="mb-8 border-b border-amber-500/30 pb-6">
          <div className="text-xs uppercase tracking-widest text-amber-400 font-semibold mb-2">
            BTU · 2026
          </div>
          <h1 className="text-3xl font-serif text-amber-200 tracking-wide mb-2">
            {title}
          </h1>
          {subtitle ? (
            <p className="text-slate-300 text-sm leading-relaxed">{subtitle}</p>
          ) : null}
        </div>

        <div className="prose prose-invert max-w-none text-slate-200 leading-relaxed text-sm space-y-6">
          {children}
        </div>

        <div className="mt-12 pt-8 border-t border-slate-800 flex justify-center">
          <Seal locale={locale} />
        </div>
      </main>

      <Footer locale={locale} />
    </div>
  )
}
