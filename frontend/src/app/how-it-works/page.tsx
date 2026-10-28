'use client'

import Link from 'next/link'

import { InfoLayout } from '@/components/info-layout'
import { useLocale } from '@/i18n/use-locale'

export default function HowItWorksPage() {
  const [locale, setLocale] = useLocale()

  return (
    <InfoLayout
      locale={locale}
      onLocale={setLocale}
      title={locale === 'ka' ? 'როგორ მუშაობს' : 'How It Works'}
      subtitle={
        locale === 'ka'
          ? 'ციფრული პასპორტის შექმნის, ვერსიონირებისა და ვერიფიკაციის ეტაპები'
          : 'The lifecycle of credential creation, versioning, and cryptographic verification'
      }
    >
      {locale === 'ka' ? (
        <>
          <div className="grid gap-6">
            <div className="bg-[#1e293b]/50 border border-slate-700/60 rounded-lg p-5">
              <span className="text-amber-400 font-bold text-xs uppercase tracking-wider block mb-1">
                ნაბიჯი 1
              </span>
              <h3 className="text-lg font-serif text-slate-100 mb-2">
                უნარების რეგისტრაცია და სინქრონიზაცია
              </h3>
              <p className="text-sm text-slate-300">
                სტუდენტის მიერ კურსის ან პროექტის დასრულების შემდეგ, მონაცემები
                ფიქსირდება BTU-ს საგანმანათლებლო ცხრილში. სისტემა ავტომატურად
                ახდენს მონაცემების სინქრონიზაციას და ამოწმებს უნარების
                ჩამონათვალს.
              </p>
            </div>

            <div className="bg-[#1e293b]/50 border border-slate-700/60 rounded-lg p-5">
              <span className="text-amber-400 font-bold text-xs uppercase tracking-wider block mb-1">
                ნაბიჯი 2
              </span>
              <h3 className="text-lg font-serif text-slate-100 mb-2">
                ვერსიონირება და PDF გენერაცია
              </h3>
              <p className="text-sm text-slate-300">
                თუ სტუდენტს დაემატა ახალი უნარი, სისტემა ქმნის ახალ ვერსიას (V1,
                V2...) და ახალ უნიკალურ ვერიფიკაციის კოდს (მაგ.{' '}
                <code>K9M2-N3P4-Q5R6-S7T8</code>). ამავე დროს ავტომატურად
                მზადდება ოფიციალური ორენოვანი PDF პასპორტი უნივერსიტეტის ბეჭდითა
                და ბეჯებით.
              </p>
            </div>

            <div className="bg-[#1e293b]/50 border border-slate-700/60 rounded-lg p-5">
              <span className="text-amber-400 font-bold text-xs uppercase tracking-wider block mb-1">
                ნაბიჯი 3
              </span>
              <h3 className="text-lg font-serif text-slate-100 mb-2">
                ბლოკჩეინზე დაფიქსირება (Anchor)
              </h3>
              <p className="text-sm text-slate-300">
                პასპორტის მონაცემებისგან დაგენერირებული კრიპტოგრაფიული ჰეში
                იგზავნება Polygon Amoy Testnet-ის სმარტ-კონტრაქტში BTU-ს
                ოფიციალური გამცემი საფულის მიერ. ეს გამორიცხავს მონაცემების
                უკანა თარიღით შეცვლას ან გაყალბებას.
              </p>
            </div>

            <div className="bg-[#1e293b]/50 border border-slate-700/60 rounded-lg p-5">
              <span className="text-amber-400 font-bold text-xs uppercase tracking-wider block mb-1">
                ნაბიჯი 4
              </span>
              <h3 className="text-lg font-serif text-slate-100 mb-2">
                მარტივი საჯარო ვერიფიკაცია
              </h3>
              <p className="text-sm text-slate-300">
                ნებისმიერ დამსაქმებელს ან პარტნიორს შეუძლია შეიყვანოს
                ვერიფიკაციის კოდი <code>/verify</code> გვერდზე და მყისიერად
                იხილოს სტუდენტის უნარები, გაცემის თარიღი, ვერსიის სტატუსი და
                ბლოკჩეინის ტრანზაქციის ბმული.
              </p>
            </div>
          </div>

          <div className="pt-4">
            <Link
              href="/"
              className="text-amber-400 hover:text-amber-300 underline font-medium"
            >
              ← მთავარ გვერდზე დაბრუნება
            </Link>
          </div>
        </>
      ) : (
        <>
          <div className="grid gap-6">
            <div className="bg-[#1e293b]/50 border border-slate-700/60 rounded-lg p-5">
              <span className="text-amber-400 font-bold text-xs uppercase tracking-wider block mb-1">
                Step 1
              </span>
              <h3 className="text-lg font-serif text-slate-100 mb-2">
                Skill Registration & Sync
              </h3>
              <p className="text-sm text-slate-300">
                When students complete approved AI courses or practical
                projects, entries are logged in the BTU academic roster. The
                backend runs automated syncs, identifying verified achievements
                with strict idempotency.
              </p>
            </div>

            <div className="bg-[#1e293b]/50 border border-slate-700/60 rounded-lg p-5">
              <span className="text-amber-400 font-bold text-xs uppercase tracking-wider block mb-1">
                Step 2
              </span>
              <h3 className="text-lg font-serif text-slate-100 mb-2">
                Versioning & Document Generation
              </h3>
              <p className="text-sm text-slate-300">
                Whenever skills change, a new passport version is issued (V1,
                V2...) along with a dedicated verification code (e.g.{' '}
                <code>K9M2-N3P4-Q5R6-S7T8</code>). High-resolution bilingual PDF
                passports are compiled with cryptographic fingerprints and
                visual badges.
              </p>
            </div>

            <div className="bg-[#1e293b]/50 border border-slate-700/60 rounded-lg p-5">
              <span className="text-amber-400 font-bold text-xs uppercase tracking-wider block mb-1">
                Step 3
              </span>
              <h3 className="text-lg font-serif text-slate-100 mb-2">
                Cryptographic Testnet Anchoring
              </h3>
              <p className="text-sm text-slate-300">
                A SHA-256 fingerprint of the credential is submitted to the
                Polygon Amoy Testnet smart contract by the BTU issuer wallet.
                This permanently timestamps the credentials without publishing
                private student data.
              </p>
            </div>

            <div className="bg-[#1e293b]/50 border border-slate-700/60 rounded-lg p-5">
              <span className="text-amber-400 font-bold text-xs uppercase tracking-wider block mb-1">
                Step 4
              </span>
              <h3 className="text-lg font-serif text-slate-100 mb-2">
                Public Instant Verification
              </h3>
              <p className="text-sm text-slate-300">
                Anyone can verify credentials by entering the verification code
                on the <code>/verify</code> page. The system displays the active
                status, version history, authenticated skills, and direct link
                to the PolygonScan blockchain explorer.
              </p>
            </div>
          </div>

          <div className="pt-4">
            <Link
              href="/"
              className="text-amber-400 hover:text-amber-300 underline font-medium"
            >
              ← Back to Home
            </Link>
          </div>
        </>
      )}
    </InfoLayout>
  )
}
