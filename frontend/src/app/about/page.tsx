'use client'

import Link from 'next/link'

import { InfoLayout } from '@/components/info-layout'
import { useLocale } from '@/i18n/use-locale'

export default function AboutPage() {
  const [locale, setLocale] = useLocale()

  return (
    <InfoLayout
      locale={locale}
      onLocale={setLocale}
      title={locale === 'ka' ? 'პროექტის შესახებ' : 'About the Project'}
      subtitle={
        locale === 'ka'
          ? 'BTU AI უნარების ციფრული პასპორტის პლატფორმის ხედვა და მისია'
          : 'Mission and vision of the BTU AI Skills Digital Passport platform'
      }
    >
      {locale === 'ka' ? (
        <>
          <section className="space-y-3">
            <h2 className="text-xl font-serif text-amber-300">
              BTU AI ციფრული პასპორტი
            </h2>
            <p>
              ბიზნესისა და ტექნოლოგიების უნივერსიტეტის (BTU) ხელოვნური
              ინტელექტის ციფრული პასპორტი არის ინოვაციური აკადემიური ინიციატივა.
              პლატფორმის მიზანია სტუდენტების მიერ ათვისებული ხელოვნური
              ინტელექტის უნარებისა და კომპეტენციების აღრიცხვა, გამჭვირვალე
              შეფასება და კრიპტოგრაფიული დადასტურება.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-xl font-serif text-amber-300">
              ვისთვის არის შექმნილი?
            </h2>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong>სტუდენტებისთვის:</strong> საშუალებას აძლევს სტუდენტებს
                ჰქონდეთ ოფიციალური ციფრული პასპორტი, მუდმივი ID-ით, უნარების
                ისტორიითა და ჩამოტვირთვადი ორენოვანი (ქართულ-ინგლისური)
                სერტიფიკატის PDF ფაილით.
              </li>
              <li>
                <strong>დამსაქმებლებისთვის:</strong> უზრუნველყოფს უნარების
                მყისიერ და უტყუარ ვერიფიკაციას საჯარო კოდის მეშვეობით, მესამე
                მხარის ჩარევის გარეშე.
              </li>
              <li>
                <strong>უნივერსიტეტისთვის:</strong> ამარტივებს აკადემიური
                მიღწევების მართვას ავტომატური სინქრონიზაციის საშუალებით.
              </li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="text-xl font-serif text-amber-300">
              სატესტო გარემო და ბლოკჩეინი
            </h2>
            <p>
              მონაცემთა ავთენტურობის დასადასტურებლად სისტემა იყენებს Polygon
              Amoy Testnet-ს. ბლოკჩეინზე არასდროს იწერება სტუდენტის პირადი
              მონაცემები — ინახება მხოლოდ კრიპტოგრაფიული ჰეში (Proof of
              Integrity).
            </p>
          </section>

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
          <section className="space-y-3">
            <h2 className="text-xl font-serif text-amber-300">
              BTU AI Skills Digital Passport
            </h2>
            <p>
              The BTU AI Skills Digital Passport is an academic credentialing
              platform developed by Business and Technology University (Tbilisi,
              Georgia). It provides verifiable proof of AI literacy, engineering
              competencies, and project-based skills acquired by students.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-xl font-serif text-amber-300">
              Core Objectives
            </h2>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong>For Students:</strong> A permanent digital identity with
                versioned skill records and official bilingual PDF credentials.
              </li>
              <li>
                <strong>For Employers & Partners:</strong> Single-click instant
                verification of skills with cryptographic guarantees on public
                testnets.
              </li>
              <li>
                <strong>For Academia:</strong> Automated synchronization from
                university course registries directly to immutable credential
                records.
              </li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="text-xl font-serif text-amber-300">
              Blockchain Integrity
            </h2>
            <p>
              To guarantee that records cannot be altered retroactively, each
              passport version is anchored to the Polygon Amoy Testnet. Only
              zero-knowledge identifiers and SHA-256 digests are recorded
              on-chain, preserving absolute student privacy.
            </p>
          </section>

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
