'use client'

import Link from 'next/link'

import { InfoLayout } from '@/components/info-layout'
import { useLocale } from '@/i18n/use-locale'

export default function AboutPage() {
  const [locale, setLocale] = useLocale()

  const en = locale === 'en'

  return (
    <InfoLayout
      locale={locale}
      onLocale={setLocale}
      folio="04"
      chapterLabel={en ? 'AI SKILLS PASSPORT' : 'AI უნარების პასპორტი'}
      chapterBody={
        en
          ? 'A trusted record of learning, achievement, and applied intelligence.'
          : 'სწავლის, მიღწევებისა და გამოყენებითი ინტელექტის სანდო ჩანაწერი.'
      }
      title={en ? 'About the Project' : 'პროექტის შესახებ'}
    >
      <Link className="back-link" href="/">
        ← {en ? 'Back to home' : 'მთავარ გვერდზე დაბრუნება'}
      </Link>

      <p className="intro">
        {en
          ? 'The BTU AI Skills Digital Passport is an academic credentialing platform that issues verifiable, blockchain-anchored skill records to Business and Technology University students.'
          : 'BTU AI უნარების ციფრული პასპორტი არის აკადემიური სერტიფიკაციის პლატფორმა, რომელიც გასცემს ბლოკჩეინ-დაფიქსირებულ, ვერიფიცირებად უნარების ჩანაწერებს ბიზნესისა და ტექნოლოგიების უნივერსიტეტის სტუდენტებზე.'}
      </p>

      <h2>{en ? 'Who is it for?' : 'ვისთვისაა?'}</h2>
      <p>
        {en
          ? 'Students receive a permanent passport ID with a versioned skill history and downloadable bilingual PDFs. Employers can instantly verify any code without any middleman. The university automates credential management through sheet synchronisation.'
          : 'სტუდენტები იღებენ მუდმივ პასპორტის ID-ს ვერსიული უნარების ისტორიით და ჩამოტვირთვადი ორენოვანი PDF-ებით. დამსაქმებლებს შეუძლიათ ნებისმიერი კოდის მყისიერი ვერიფიკაცია შუამავლის გარეშე. უნივერსიტეტი ასახელებს სერტიფიკატების მართვას ცხრილის სინქრონიზაციის საშუალებით.'}
      </p>

      <h2>{en ? 'Blockchain integrity' : 'ბლოკჩეინის მთლიანობა'}</h2>
      <p>
        {en
          ? 'Each passport version is anchored to the Polygon Amoy testnet. Only a SHA-256 digest and a hashed verification identifier reach the chain — no personal data is ever published on-chain.'
          : 'პასპორტის თითოეული ვერსია ფიქსირდება Polygon Amoy Testnet-ზე. ჯაჭვს მხოლოდ SHA-256 დაიჯესტი და ჰეშირებული ვერიფიკაციის იდენტიფიკატორი ეგზავნება — პირადი მონაცემები ბლოკჩეინზე არასდროს ქვეყნდება.'}
      </p>
    </InfoLayout>
  )
}
