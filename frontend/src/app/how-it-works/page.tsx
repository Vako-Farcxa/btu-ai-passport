'use client'

import Link from 'next/link'

import { InfoLayout } from '@/components/info-layout'
import { useLocale } from '@/i18n/use-locale'

export default function HowItWorksPage() {
  const [locale, setLocale] = useLocale()

  const en = locale === 'en'

  return (
    <InfoLayout
      locale={locale}
      onLocale={setLocale}
      folio="05"
      chapterLabel={en ? 'AI SKILLS PASSPORT' : 'AI უნარების პასპორტი'}
      chapterBody={
        en
          ? 'A trusted record of learning, achievement, and applied intelligence.'
          : 'სწავლის, მიღწევებისა და გამოყენებითი ინტელექტის სანდო ჩანაწერი.'
      }
      title={en ? 'How it works' : 'როგორ მუშაობს'}
    >
      <Link className="back-link" href="/">
        ← {en ? 'Back to home' : 'მთავარ გვერდზე დაბრუნება'}
      </Link>

      <p className="intro">
        {en ? (
          <>
            Four steps take a student&apos;s achievement from spreadsheet row to
            anchored credential.
          </>
        ) : (
          <>
            ოთხი ნაბიჯი გარდაქმნის სტუდენტის მიღწევას ცხრილის სტრიქონიდან
            კრიპტოგრაფიულად დაფიქსირებულ სერტიფიკატად.
          </>
        )}
      </p>

      <h2>{en ? '1 · Sync from the sheet' : '1 · სინქრონიზაცია ცხრილიდან'}</h2>
      <p>
        {en ? (
          <>
            The backend reads BTU&apos;s official Google Sheet every 15 minutes,
            detects new or changed rows, and creates or updates passport records
            idempotently.
          </>
        ) : (
          <>
            Backend ყოველ 15 წუთში კითხულობს BTU-ს ოფიციალურ Google Sheets-ს,
            ამოიცნობს ახალ ან შეცვლილ სტრიქონებს და ქმნის ან განაახლებს
            პასპორტის ჩანაწერებს იდემპოტენტურად.
          </>
        )}
      </p>

      <h2>
        {en
          ? '2 · Version & generate PDF'
          : '2 · ვერსიონირება და PDF გენერაცია'}
      </h2>
      <p>
        {en ? (
          <>
            Each changed skill set produces a new version (V1, V2&hellip;) with
            a unique verification code and a bilingual EN/KA PDF rendered from
            BTU&apos;s official template.
          </>
        ) : (
          <>
            შეცვლილი უნარების თითოეული ნაკრები ქმნის ახალ ვერსიას (V1, V2…)
            უნიკალური ვერიფიკაციის კოდით და ორენოვანი EN/KA PDF-ით, BTU-ს
            ოფიციალური შაბლონიდან.
          </>
        )}
      </p>

      <h2>{en ? '3 · Anchor on-chain' : '3 · ბლოკჩეინზე დაფიქსირება'}</h2>
      <p>
        {en ? (
          <>
            A SHA-256 fingerprint of the credential is submitted to the BTU
            issuer smart contract on Polygon Amoy. Only the hash reaches the
            chain &mdash; names and emails stay off-chain.
          </>
        ) : (
          <>
            სერტიფიკატის SHA-256 ანაბეჭდი იგზავნება BTU-ს გამცემ სმარტ
            კონტრაქტში Polygon Amoy-ზე. ჯაჭვს მხოლოდ ჰეში ეხება — სახელები და
            ელ-ფოსტები ჯაჭვის გარეთ რჩება.
          </>
        )}
      </p>

      <h2>{en ? '4 · Public verify' : '4 · საჯარო ვერიფიკაცია'}</h2>
      <p>
        {en ? (
          <>
            Anyone with a verification code visits /verify, enters the code, and
            sees the official skill list, version status, holder name, and a
            link to the blockchain transaction.
          </>
        ) : (
          <>
            ნებისმიერი ვერიფიკაციის კოდის მქონე პირი ეწვევა /verify-ს, შეიყვანს
            კოდს და ნახავს ოფიციალური უნარების სიას, ვერსიის სტატუსს, მფლობელის
            სახელს და ბლოკჩეინის ტრანზაქციის ბმულს.
          </>
        )}
      </p>
    </InfoLayout>
  )
}
