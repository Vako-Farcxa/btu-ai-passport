'use client'

import Link from 'next/link'

import { InfoLayout } from '@/components/info-layout'
import { useLocale } from '@/i18n/use-locale'

export default function PrivacyPage() {
  const [locale, setLocale] = useLocale()

  return (
    <InfoLayout
      locale={locale}
      onLocale={setLocale}
      title={locale === 'ka' ? 'კონფიდენციალურობის პოლიტიკა' : 'Privacy Policy'}
      subtitle={
        locale === 'ka'
          ? 'როგორ ვიცავთ სტუდენტების მონაცემებსა და პირად ინფორმაციას'
          : 'How we safeguard student personal information and academic data'
      }
    >
      {locale === 'ka' ? (
        <>
          <section className="space-y-3">
            <h2 className="text-xl font-serif text-amber-300">
              მონაცემთა მინიმიზაცია
            </h2>
            <p>
              BTU AI ციფრული პასპორტის სისტემა შექმნილია მონაცემთა მკაცრი
              მინიმიზაციის პრინციპით. ჩვენ ვაგროვებთ მხოლოდ იმ ინფორმაციას, რაც
              აუცილებელია აკადემიური უნარების დასადასტურებლად: სტუდენტის სახელი
              და გვარი, BTU-ს საუნივერსიტეტო ელფოსტა (<code>@btu.edu.ge</code>)
              და მიღწეული AI უნარების ჩამონათვალი.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-xl font-serif text-amber-300">
              ბლოკჩეინის კონფიდენციალურობა
            </h2>
            <p>
              საჯარო ბლოკჩეინზე (Polygon Amoy Testnet) <strong>არასდროს</strong>{' '}
              ინახება სტუდენტის სახელი, ელფოსტა, პირადი ნომერი ან სხვა
              მაიდენტიფიცირებელი დეტალები.
            </p>
            <p>ბლოკჩეინზე ფიქსირდება მხოლოდ:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>კრიპტოგრაფიული ჰეში (SHA-256 Digest)</li>
              <li>დაჰეშირებული შიდა ვერიფიკაციის იდენტიფიკატორი</li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="text-xl font-serif text-amber-300">
              საჯარო ვერიფიკაცია
            </h2>
            <p>
              საჯარო ვერიფიკაციის გვერდი აჩვენებს სტუდენტის სახელსა და ოფიციალურ
              უნარებს მხოლოდ იმ პირებისთვის, ვისაც სტუდენტმა თავად გაუზიარა
              უნიკალური ვერიფიკაციის კოდი ან ბმული. სტუდენტის ელფოსტა და შიდა
              მონაცემთა ბაზის ID არასდროს არის ხილული საჯარო ვერიფიკაციის
              ინტერფეისში.
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
              Data Minimization
            </h2>
            <p>
              The BTU AI Digital Passport platform follows strict data
              minimization principles. We only process student information
              necessary for academic credential verification: full name,
              official university email (<code>@btu.edu.ge</code>), and verified
              course competency records.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-xl font-serif text-amber-300">
              Zero-Knowledge On-Chain Anchoring
            </h2>
            <p>
              No personal student data is <strong>ever</strong> published or
              anchored to the blockchain. The Polygon Amoy testnet receives
              only:
            </p>
            <ul className="list-disc pl-6 space-y-1">
              <li>A one-way cryptographic SHA-256 content digest</li>
              <li>A salted, hashed internal verification identifier</li>
            </ul>
            <p>
              It is mathematically impossible to reconstruct personal identity
              or skill descriptions from the on-chain payload.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-xl font-serif text-amber-300">
              Verification Access Control
            </h2>
            <p>
              Credential details (student name, acquired badges, issuance dates)
              are disclosed on the verification interface only to parties
              possessing the holder&apos;s specific verification code. Student
              email addresses, internal system IDs, and private records are
              strictly redacted from all public API responses.
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
