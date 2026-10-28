import Link from 'next/link'

import { messages, type Locale } from '@/i18n/messages'

export function Footer({ locale }: { locale: Locale }) {
  const copy = messages[locale]

  return (
    <footer className="w-full mt-auto border-t border-[rgba(212,175,55,0.2)] bg-[#0b1424] text-[#cbd5e1] py-8 px-4 text-xs transition-colors">
      <div className="max-w-4xl mx-auto flex flex-col gap-5">
        {/* Notices */}
        <div className="flex flex-col gap-2 rounded bg-[#132238]/60 p-4 border border-[rgba(212,175,55,0.15)] leading-relaxed">
          <p className="text-[13px] text-amber-200/90 font-medium">
            <span className="font-semibold text-amber-400">✦ </span>
            {copy.footerTestnetNotice}
          </p>
          <p className="text-[#94a3b8] text-[12px]">{copy.footerDisclaimer}</p>
        </div>

        {/* Links and Copyright */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-2 border-t border-slate-800/80">
          <div className="flex items-center gap-2">
            <span className="font-serif tracking-widest text-amber-400 font-semibold">
              BTU
            </span>
            <span className="text-slate-500">·</span>
            <span className="text-slate-400">
              © {new Date().getFullYear()} {copy.universityName}
            </span>
          </div>

          <nav
            className="flex items-center gap-6"
            aria-label="Footer Navigation"
          >
            <Link
              href="/about"
              className="text-slate-300 hover:text-amber-300 transition-colors underline-offset-4 hover:underline"
            >
              {copy.navAbout}
            </Link>
            <Link
              href="/how-it-works"
              className="text-slate-300 hover:text-amber-300 transition-colors underline-offset-4 hover:underline"
            >
              {copy.navHowItWorks}
            </Link>
            <Link
              href="/privacy"
              className="text-slate-300 hover:text-amber-300 transition-colors underline-offset-4 hover:underline"
            >
              {copy.navPrivacy}
            </Link>
          </nav>
        </div>
      </div>
    </footer>
  )
}
