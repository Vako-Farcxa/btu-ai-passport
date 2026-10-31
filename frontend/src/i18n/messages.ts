export type Locale = 'en' | 'ka'
export type Outcome =
  'valid' | 'outdated' | 'revoked' | 'pending' | 'not_found' | 'error'
export type BadgeCode = 'BDG-AI-001' | 'BDG-AI-002' | 'BDG-AI-003'
type BadgeLevel = { title: string; text: string }

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
  copyShareLink: string
  shareLinkCopied: string
  shareLinkFailed: string
  newerVersionNotice: string
  universityName: string
  sealEstablished: string
  badgeLevels: Record<BadgeCode, BadgeLevel>
  copyCode: string
  codeCopied: string
  copyCodeFailed: string
  flagIssue: string
  flagDialogTitle: string
  flagCommentLabel: string
  flagCommentHint: string
  flagSubmit: string
  flagSending: string
  flagCancel: string
  flagClose: string
  flagSent: string
  flagTooShort: string
  flagTooLong: string
  flagAlreadyOpen: string
  flagRateLimited: string
  flagError: string
  flagLoadError: string
  flagStatuses: Record<'open' | 'resolved' | 'dismissed', string>
  flagBadgeLabel: string
  flagDetailsTitle: string
  flagYourComment: string
  flagReplyTitle: string
  flagNoReply: string
  flagSentOn: string
  flagAnsweredOn: string
  myFlags: string
  myFlagsTitle: string
  myFlagsEmpty: string
  newReply: string
  pendingNotice: string
  revokedNotice: string
  revokedNoticeNoDate: string
  passportRevokedTitle: string
  passportRevoked: string
  versionRevokedBadge: string
  versionRevokedNote: string
  versionRevokedPdf: string
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
    skills: 'Skills',
    dateUnavailable: 'Date unavailable',
    transaction: 'Public transaction',
    language: 'Language',
    outcomes: {
      valid: 'Valid',
      outdated: 'Outdated version',
      revoked: 'Revoked',
      pending: 'Pending on-chain confirmation',
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
    landingNote: 'STUDENT HACKATHON PROJECT · TBILISI',
    holderLabel: 'Passport holder',
    passportEyebrow: 'BTU · PASSPORT 01',
    verifyEyebrow: 'BTU · VERIFICATION',
    copyShareLink: 'Copy share link',
    shareLinkCopied: 'Share link copied',
    shareLinkFailed: 'Could not copy. Copy this link manually:',
    universityName: 'Business and Technology University',
    sealEstablished: 'EST. 2016',
    badgeLevels: {
      'BDG-AI-001': {
        title: 'AI Skill · Focused learning',
        text: 'Awarded for focused learning of an AI skill.',
      },
      'BDG-AI-002': {
        title: 'AI Applied Skill · Applied learning',
        text: 'Awarded for applying an AI skill in practice.',
      },
      'BDG-AI-003': {
        title: 'AI Advanced Skill · Extended academic learning',
        text: 'Awarded for extended academic learning in an AI skill.',
      },
    },
    copyCode: 'Copy code',
    codeCopied: 'Copied',
    copyCodeFailed: 'Could not copy. The code is selected: press Ctrl+C.',
    newerVersionNotice:
      'A newer version (v{version}) of this passport was issued on {date}. Ask the holder for their latest code.',
    flagIssue: 'Flag an issue',
    flagDialogTitle: 'Flag an issue with version {version}',
    flagCommentLabel: 'What looks wrong?',
    flagCommentHint: 'Between 10 and 500 characters. {count} / 500',
    flagSubmit: 'Send flag',
    flagSending: 'Sending',
    flagCancel: 'Cancel',
    flagClose: 'Close',
    flagSent: 'Thank you. Your flag was sent to the BTU team.',
    flagTooShort: 'Please write at least 10 characters.',
    flagTooLong: 'Please keep it to 500 characters or fewer.',
    flagAlreadyOpen: 'This version already has an open flag.',
    flagRateLimited:
      'You have sent several flags recently. Try again in an hour.',
    flagError: 'The flag could not be sent. Try again later.',
    flagLoadError: 'Your flags could not be loaded.',
    flagStatuses: {
      open: 'Flag open',
      resolved: 'Flag resolved',
      dismissed: 'Flag dismissed',
    },
    flagBadgeLabel: 'Flag status for version {version}: {status}. Show details',
    flagDetailsTitle: 'Flag on version {version}',
    flagYourComment: 'Your comment',
    flagReplyTitle: 'Reply from BTU',
    flagNoReply: 'No reply yet. The BTU team will look at it.',
    flagSentOn: 'Sent {date}',
    flagAnsweredOn: 'Answered {date}',
    myFlags: 'My flags',
    myFlagsTitle: 'My flags',
    myFlagsEmpty: 'You have not flagged anything.',
    newReply: 'New reply',
    pendingNotice:
      'This code exists, but its record on the blockchain is not confirmed yet. This usually takes a few minutes. Check again later. Nothing is shown until it is confirmed.',
    revokedNotice:
      'This passport version was revoked on {date}. It is no longer valid and must not be relied on.',
    revokedNoticeNoDate:
      'This passport version has been revoked. It is no longer valid and must not be relied on.',
    passportRevokedTitle: 'Passport unavailable',
    passportRevoked:
      'This passport has been revoked by BTU, so it can no longer be viewed or downloaded. If you think this is a mistake, contact the BTU AI Skills team.',
    versionRevokedBadge: 'Revoked',
    versionRevokedNote:
      'This version was revoked on {date}. Its PDF is no longer available.',
    versionRevokedPdf: 'This version was revoked, so its PDF is not available.',
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
    skills: 'უნარები',
    dateUnavailable: 'თარიღი უცნობია',
    transaction: 'საჯარო ტრანზაქცია',
    language: 'ენა',
    outcomes: {
      valid: 'ნამდვილია',
      outdated: 'მოძველებული ვერსია',
      revoked: 'გაუქმებულია',
      pending: 'ელოდება ბლოკჩეინზე დადასტურებას',
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
    landingNote: 'სტუდენტური ჰაკათონის პროექტი · თბილისი',
    holderLabel: 'პასპორტის მფლობელი',
    passportEyebrow: 'BTU · პასპორტი 01',
    verifyEyebrow: 'BTU · შემოწმება',
    copyShareLink: 'ბმულის კოპირება',
    shareLinkCopied: 'ბმული დაკოპირდა',
    shareLinkFailed: 'კოპირება ვერ მოხერხდა. დააკოპირეთ ბმული ხელით:',
    universityName: 'ბიზნესისა და ტექნოლოგიების უნივერსიტეტი',
    sealEstablished: 'დაარს. 2016',
    badgeLevels: {
      'BDG-AI-001': {
        title: 'AI უნარი · მიზნობრივი სწავლა',
        text: 'ენიჭება AI უნარის მიზნობრივი სწავლისთვის.',
      },
      'BDG-AI-002': {
        title: 'AI გამოყენებითი უნარი · გამოყენებითი სწავლა',
        text: 'ენიჭება AI უნარის პრაქტიკაში გამოყენებისთვის.',
      },
      'BDG-AI-003': {
        title: 'AI მოწინავე უნარი · გაფართოებული აკადემიური სწავლა',
        text: 'ენიჭება AI უნარში გაფართოებული აკადემიური სწავლისთვის.',
      },
    },
    copyCode: 'კოდის კოპირება',
    codeCopied: 'დაკოპირდა',
    copyCodeFailed: 'კოპირება ვერ მოხერხდა. კოდი მონიშნულია: დააჭირეთ Ctrl+C.',
    newerVersionNotice:
      'ამ პასპორტის უფრო ახალი ვერსია (v{version}) გაიცა {date}-ზე. სთხოვეთ მფლობელს უახლესი კოდი.',
    flagIssue: 'პრობლემის აღნიშვნა',
    flagDialogTitle: 'პრობლემის აღნიშვნა, ვერსია {version}',
    flagCommentLabel: 'რა არის არასწორი?',
    flagCommentHint: '10-დან 500 სიმბოლომდე. {count} / 500',
    flagSubmit: 'გაგზავნა',
    flagSending: 'იგზავნება',
    flagCancel: 'გაუქმება',
    flagClose: 'დახურვა',
    flagSent: 'გმადლობთ. თქვენი შეტყობინება გაეგზავნა BTU-ის გუნდს.',
    flagTooShort: 'დაწერეთ მინიმუმ 10 სიმბოლო.',
    flagTooLong: 'მაქსიმუმ 500 სიმბოლო.',
    flagAlreadyOpen: 'ამ ვერსიაზე უკვე არის ღია შეტყობინება.',
    flagRateLimited:
      'ახლახან რამდენიმე შეტყობინება გააგზავნეთ. სცადეთ ერთ საათში.',
    flagError: 'შეტყობინება ვერ გაიგზავნა. სცადეთ მოგვიანებით.',
    flagLoadError: 'თქვენი შეტყობინებები ვერ ჩაიტვირთა.',
    flagStatuses: {
      open: 'შეტყობინება ღიაა',
      resolved: 'შეტყობინება გადაწყდა',
      dismissed: 'შეტყობინება უარყოფილია',
    },
    flagBadgeLabel:
      'შეტყობინების სტატუსი, ვერსია {version}: {status}. დეტალების ნახვა',
    flagDetailsTitle: 'შეტყობინება, ვერსია {version}',
    flagYourComment: 'თქვენი კომენტარი',
    flagReplyTitle: 'BTU-ის პასუხი',
    flagNoReply: 'პასუხი ჯერ არ არის. BTU-ის გუნდი განიხილავს.',
    flagSentOn: 'გაიგზავნა {date}',
    flagAnsweredOn: 'გაეცა პასუხი {date}',
    myFlags: 'ჩემი შეტყობინებები',
    myFlagsTitle: 'ჩემი შეტყობინებები',
    myFlagsEmpty: 'ჯერ არაფერი გაგიგზავნიათ.',
    newReply: 'ახალი პასუხი',
    pendingNotice:
      'ეს კოდი არსებობს, მაგრამ მისი ჩანაწერი ბლოკჩეინზე ჯერ არ დადასტურებულა. ეს ჩვეულებრივ რამდენიმე წუთს გრძელდება. სცადეთ მოგვიანებით. დადასტურებამდე არაფერი ნაჩვენებია.',
    revokedNotice:
      'ეს პასპორტის ვერსია გაუქმდა {date}. ის აღარ არის ნამდვილი და მასზე დაყრდნობა არ შეიძლება.',
    revokedNoticeNoDate:
      'ეს პასპორტის ვერსია გაუქმებულია. ის აღარ არის ნამდვილი და მასზე დაყრდნობა არ შეიძლება.',
    passportRevokedTitle: 'პასპორტი მიუწვდომელია',
    passportRevoked:
      'ეს პასპორტი BTU-მ გააუქმა, ამიტომ მისი ნახვა და გადმოწერა აღარ შეიძლება. თუ ფიქრობთ, რომ ეს შეცდომაა, დაუკავშირდით BTU-ის AI უნარების გუნდს.',
    versionRevokedBadge: 'გაუქმებულია',
    versionRevokedNote:
      'ეს ვერსია გაუქმდა {date}. მისი PDF აღარ არის ხელმისაწვდომი.',
    versionRevokedPdf: 'ეს ვერსია გაუქმებულია, ამიტომ მისი PDF მიუწვდომელია.',
  },
}

export function preferredLocale(language: string): Locale {
  const value = language.toLowerCase()
  if (value.startsWith('ka')) return 'ka'
  if (value.startsWith('en')) return 'en'
  return 'ka'
}
