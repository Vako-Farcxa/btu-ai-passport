export type Locale = 'en' | 'ka'
export type Outcome = 'valid' | 'outdated' | 'not_found' | 'error'

type Copy = {
  title: string
  intro: string
  codeLabel: string
  check: string
  checking: string
  prompt: string
  latest: string
  notLatest: string
  skills: string
  dateUnavailable: string
  transaction: string
  language: string
  outcomes: Record<Outcome, string>
  homeTitle: string
  homeIntro: string
  signIn: string
  signInUnavailable: string
  verifyLink: string
  openPassport: string
  domainNotAllowed: string
  emptyPassport: string
  loading: string
  signInRequired: string
  passportError: string
  passportTitle: string
  passportId: string
  currentVersion: string
  history: string
  verificationCode: string
  versionLabel: string
  downloadPdf: string
  preparingPdf: string
  pdfNotReady: string
  back: string
  chapter: string
  chapterBody: string
  landingNote: string
  holderLabel: string
  passportEyebrow: string
  verifyEyebrow: string
}

export const messages: Record<Locale, Copy> = {
  en: {
    title: 'Verify a passport',
    intro: 'Enter the verification code from a BTU AI Skills passport.',
    codeLabel: 'Verification code',
    check: 'Check',
    checking: 'Checking',
    prompt: 'Enter a verification code',
    latest: 'This is the latest version',
    notLatest: 'This is not the latest version',
    skills: 'Official skills',
    dateUnavailable: 'Date unavailable',
    transaction: 'Public transaction',
    language: 'Language',
    outcomes: {
      valid: 'Valid',
      outdated: 'Outdated version',
      not_found: 'Not found',
      error: 'Error',
    },
    homeTitle: 'BTU AI Skills Passport',
    homeIntro:
      'Sign in with your btu.edu.ge Google account, or check a verification code.',
    signIn: 'Sign in with Google',
    signInUnavailable: 'Google sign-in is not configured yet.',
    verifyLink: 'Verify a code',
    openPassport: 'Open passport',
    domainNotAllowed:
      'This Google account is not a btu.edu.ge address. No passport is available.',
    emptyPassport: 'No passport is available yet.',
    loading: 'Loading',
    signInRequired: 'Sign in to see your passport.',
    passportError: 'The passport could not be loaded.',
    passportTitle: 'Your passport',
    passportId: 'Passport ID',
    currentVersion: 'Current version',
    history: 'Version history',
    verificationCode: 'Verification code',
    versionLabel: 'Version',
    downloadPdf: 'Download PDF',
    preparingPdf: 'Preparing…',
    pdfNotReady: "This version's PDF is not ready yet.",
    back: 'Back to home',
    chapter: 'AI SKILLS PASSPORT',
    chapterBody:
      'A trusted record of learning, achievement, and applied intelligence.',
    landingNote: 'OFFICIAL DIGITAL CREDENTIAL · TBILISI',
    holderLabel: 'Passport holder',
    passportEyebrow: 'BTU · PASSPORT 01',
    verifyEyebrow: 'BTU · VERIFICATION',
  },
  ka: {
    title: 'პასპორტის შემოწმება',
    intro: 'შეიყვანეთ BTU AI უნარების პასპორტში მითითებული ვერიფიკაციის კოდი.',
    codeLabel: 'შემოწმების კოდი',
    check: 'შემოწმება',
    checking: 'მოწმდება',
    prompt: 'შეიყვანეთ ვერიფიკაციის კოდი',
    latest: 'ეს პასპორტის უახლესი ვერსიაა',
    notLatest: 'ეს არ არის უახლესი ვერსია',
    skills: 'ოფიციალური უნარები',
    dateUnavailable: 'თარიღი უცნობია',
    transaction: 'საჯარო ტრანზაქცია',
    language: 'ენა',
    outcomes: {
      valid: 'ნამდვილია',
      outdated: 'მოძველებული ვერსია',
      not_found: 'ვერ მოიძებნა',
      error: 'შეცდომა',
    },
    homeTitle: 'BTU AI უნარების პასპორტი',
    homeIntro:
      'შედით btu.edu.ge-ის Google ანგარიშით, ან შეამოწმეთ ვერიფიკაციის კოდი.',
    signIn: 'Google-ით შესვლა',
    signInUnavailable: 'Google-ით შესვლა ჯერ არ არის კონფიგურირებული.',
    verifyLink: 'კოდის შემოწმება',
    openPassport: 'პასპორტის გახსნა',
    domainNotAllowed:
      'ეს Google ანგარიში არ არის btu.edu.ge მისამართი. პასპორტი მიუწვდომელია.',
    emptyPassport: 'პასპორტი ჯერ არ არის ხელმისაწვდომი.',
    loading: 'იტვირთება',
    signInRequired: 'პასპორტის სანახავად შედით ანგარიშში.',
    passportError: 'პასპორტის ჩატვირთვა ვერ მოხერხდა.',
    passportTitle: 'შენი პასპორტი',
    passportId: 'პასპორტის ID',
    currentVersion: 'მიმდინარე ვერსია',
    history: 'ვერსიების ისტორია',
    verificationCode: 'ვერიფიკაციის კოდი',
    versionLabel: 'ვერსია',
    downloadPdf: 'PDF-ის ჩამოტვირთვა',
    preparingPdf: 'მზადდება…',
    pdfNotReady: 'ამ ვერსიის PDF ჯერ მზად არ არის.',
    back: 'მთავარ გვერდზე დაბრუნება',
    chapter: 'AI უნარების პასპორტი',
    chapterBody:
      'სწავლის, მიღწევებისა და გამოყენებითი ინტელექტის სანდო ჩანაწერი.',
    landingNote: 'ოფიციალური ციფრული დოკუმენტი · თბილისი',
    holderLabel: 'პასპორტის მფლობელი',
    passportEyebrow: 'BTU · პასპორტი 01',
    verifyEyebrow: 'BTU · შემოწმება',
  },
}

export function preferredLocale(language: string): Locale {
  const value = language.toLowerCase()
  if (value.startsWith('ka')) return 'ka'
  if (value.startsWith('en')) return 'en'
  return 'ka'
}
