'use client'

import Link from 'next/link'

import { InfoLayout } from '@/components/info-layout'
import { useLocale } from '@/i18n/use-locale'

export default function PrivacyPage() {
  const [locale, setLocale] = useLocale()

  const en = locale === 'en'

  return (
    <InfoLayout
      locale={locale}
      onLocale={setLocale}
      folio="06"
      chapterLabel={en ? 'AI SKILLS PASSPORT' : 'AI უნარების პასპორტი'}
      chapterBody={
        en
          ? 'A trusted record of learning, achievement, and applied intelligence.'
          : 'სწავლის, მიღწევებისა და გამოყენებითი ინტელექტის სანდო ჩანაწერი.'
      }
      title={en ? 'Privacy policy' : 'კონფიდენციალურობის პოლიტიკა'}
    >
      <Link className="back-link" href="/">
        ← {en ? 'Back to home' : 'მთავარ გვერდზე დაბრუნება'}
      </Link>

      <p className="intro">
        {en
          ? 'We collect only the minimum data needed to issue and verify academic credentials, and we never publish personal information on any public blockchain.'
          : 'ჩვენ ვაგროვებთ მხოლოდ მინიმალურ მონაცემებს, რომლებიც საჭიროა აკადემიური სერტიფიკატების გასაცემად და სავერიფიკაციოდ, და არასდროს ვაქვეყნებთ პირად ინფორმაციას საჯარო ბლოკჩეინზე.'}
      </p>

      <h2>{en ? 'What we store' : 'რას ვინახავთ'}</h2>
      <p>
        {en
          ? 'We store your full name, official BTU email address, and the list of AI skills you have earned. This data is used solely to generate your passport and let you sign in.'
          : 'ჩვენ ვინახავთ თქვენს სრულ სახელს, ოფიციალურ BTU ელ-ფოსტის მისამართს და AI უნარების სიას, რომლებიც თქვენ მიგიღიათ. ეს მონაცემები გამოიყენება მხოლოდ თქვენი პასპორტის გასაცემად და სისტემაში შესაყვანად.'}
      </p>

      <h2>{en ? 'What goes on-chain' : 'რა ეგზავნება ბლოკჩეინს'}</h2>
      <p>
        {en
          ? 'Only a SHA-256 digest of the credential content and a salted, hashed verification identifier are written to Polygon Amoy. It is computationally infeasible to recover any personal detail from these values.'
          : 'Polygon Amoy-ს მხოლოდ სერტიფიკატის შინაარსის SHA-256 დაიჯესტი და დამარილებული, ჰეშირებული ვერიფიკაციის იდენტიფიკატორი ეგზავნება. ამ მნიშვნელობებიდან პერსონალური ინფორმაციის აღდგენა გამოთვლით შეუძლებელია.'}
      </p>

      <h2>
        {en ? 'Who can see your details' : 'ვინ ხედავს თქვენს მონაცემებს'}
      </h2>
      <p>
        {en
          ? 'Your name and skill list appear on the public verify page only when someone enters the specific verification code that you shared with them. Your email is never returned by any public API endpoint.'
          : 'თქვენი სახელი და უნარების სია საჯარო სავერიფიკაციო გვერდზე ჩანს მხოლოდ მაშინ, როდესაც ვინმე შეიყვანს კონკრეტულ ვერიფიკაციის კოდს, რომელიც თქვენ გაუზიარეთ. თქვენი ელ-ფოსტა ვერასდროს ბრუნდება საჯარო API-ს ბოლო წერტილიდან.'}
      </p>
    </InfoLayout>
  )
}
