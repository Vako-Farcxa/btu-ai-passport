import type { Locale } from '@/i18n/messages'
import { REPO_URL } from '@/lib/site'

export type InfoPageId = 'about' | 'privacy' | 'terms'

export type InfoSection = {
  heading: string
  /** Paragraphs, or list items when `list` is true. */
  body: readonly string[]
  list?: boolean
  link?: { label: string; href: string }
}

export type InfoPageCopy = {
  title: string
  intro: string
  sections: readonly InfoSection[]
}

export type TrustCopy = {
  /** One short line about what the project is not. */
  disclaimer: string
  projectLine: string
  team: string
  teamLabel: string
  footerLabel: string
  testnetNote: string
  navAbout: string
  navPrivacy: string
  navTerms: string
  navGithub: string
  backHome: string
  notFoundTitle: string
  notFoundBody: string
  errorTitle: string
  errorBody: string
  tryAgain: string
  removalWithEmail: string
  removalWithoutEmail: string
  pages: Record<InfoPageId, InfoPageCopy>
}

export const TEAM = [
  'Vako Partskhaladze',
  'Tazo Futuridze',
  'Giorgi Gvianishvili',
] as const

const TEAM_KA = [
  'ვაკო ფარცხალაძე',
  'თაზო ფუთურიძე',
  'გიორგი გვიანიშვილი',
] as const

const en: TrustCopy = {
  disclaimer:
    'Not an official BTU service. This is a student hackathon project, shown as a demo.',
  projectLine: 'BTU AI Skills Digital Passport · Student hackathon project',
  team: TEAM.join(' · '),
  teamLabel: 'Team',
  footerLabel: 'About this project',
  testnetNote:
    'Anchored on the Polygon Amoy test network. This is a demo: test network records have no permanence guarantee.',
  navAbout: 'About',
  navPrivacy: 'Privacy',
  navTerms: 'Terms',
  navGithub: 'GitHub',
  backHome: 'Back to home',
  notFoundTitle: 'Page not found',
  notFoundBody: 'This page does not exist or has moved.',
  errorTitle: 'Something went wrong',
  errorBody:
    'An unexpected error happened. You can try again or go back to the home page.',
  tryAgain: 'Try again',
  removalWithEmail:
    'To ask for your data to be corrected or removed, write to {email}. We will remove your passport from the database and the Sheet. The hashes already written to the blockchain stay.',
  removalWithoutEmail:
    'To ask for your data to be corrected or removed, contact the team members named on the About page. We will remove your passport from the database and the Sheet. The hashes already written to the blockchain stay.',
  pages: {
    about: {
      title: 'About this project',
      intro:
        'BTU AI Skills Digital Passport is a hackathon project made by students. It is a demo and not an official BTU service.',
      sections: [
        {
          heading: 'What a passport is',
          body: [
            'A passport is a record of the AI skills a student has been awarded. Each time skills are added, a new numbered version is issued. Every version has its own verification code and can be downloaded as a PDF in English or Georgian. The passport ID stays the same across versions.',
          ],
        },
        {
          heading: 'How verification works',
          body: [
            'Anyone can enter a verification code on the Verify page. The service looks the code up and shows the holder name, the version, the skills and whether it is the latest version. It does not show an email address, a passport ID or the code of a newer version. If a newer version exists, the result says so.',
          ],
        },
        {
          heading: 'What blockchain anchoring proves',
          body: [
            'When a version is issued, a fingerprint (hash) of its contents is written to a public blockchain. The transaction link on a verified result lets you look at that record. Anchoring shows that exactly this content existed at that time and has not been changed since. Only hashes go on the blockchain, never names, emails or skills.',
          ],
        },
        {
          heading: 'What it does not prove',
          body: [
            'It does not prove that BTU approved the skills, that the student really has them, or that the person using a code is the holder. Anyone who has a code can share it.',
          ],
        },
        {
          heading: 'Test network',
          body: [
            'Records are anchored on the Polygon Amoy test network. This is a demo: test network data can be reset or disappear, so there is no guarantee that a record stays available.',
          ],
        },
        {
          heading: 'Source code',
          body: [
            'The code is open source under the MIT license. You can read how verification and anchoring work.',
          ],
          link: {
            label: 'github.com/Vako-Farcxa/btu-ai-passport',
            href: REPO_URL,
          },
        },
        {
          heading: 'Team',
          body: [`${TEAM.join(', ')}. Student hackathon entry.`],
        },
      ],
    },
    privacy: {
      title: 'Privacy',
      intro:
        'This is a student demo. We keep the data needed to issue and verify passports and nothing more.',
      sections: [
        {
          heading: 'What we store',
          list: true,
          body: [
            'Your name and your university email address.',
            'Passport data: passport ID, awarded skills and their dates, version numbers, verification codes and PDF files.',
            'The source is a Google Sheet kept by the team. It also holds the student ID, program and education level.',
            'Sign-in goes through Supabase. We use your email address to find your passport.',
            'Reports you send about a passport: your comment, its status and any reply.',
          ],
        },
        {
          heading: 'What a verifier sees',
          body: [
            'Anyone with a code sees the holder name, the version, the skills with their dates and a link to the blockchain transaction. They do not see your email address, passport ID, student ID or the codes of other versions. A signed-in student sees only their own passport. Admins, who are the team, can see everything stored.',
          ],
        },
        {
          heading: 'Blockchain',
          body: [
            'Only hashes are written to the blockchain. They are not readable as personal data. A blockchain record cannot be deleted, even on a test network.',
          ],
        },
        {
          heading: 'Cookies',
          body: [
            'We use one cookie to remember your language, plus the Supabase sign-in session. There are no advertising or tracking cookies.',
          ],
        },
        {
          heading: 'Correction and removal',
          body: ['{removal}'],
        },
        {
          heading: 'How long we keep it',
          body: [
            'This is a demo. Data is kept while the demo runs and may be deleted at any time.',
          ],
        },
      ],
    },
    terms: {
      title: 'Terms of use',
      intro: 'Please read this before using the site.',
      sections: [
        {
          heading: 'A demo service',
          body: [
            'This site is a student hackathon project, provided as a demo. It is not an official BTU service.',
          ],
        },
        {
          heading: 'No warranty',
          body: [
            'The service is provided as is, without warranty of any kind. We do not guarantee availability, accuracy or that passports will keep working.',
          ],
        },
        {
          heading: 'Not an official credential',
          body: [
            'A verified result shows only what this demo recorded. Do not rely on it for admissions, hiring or any other official decision. Check with BTU.',
          ],
        },
        {
          heading: 'Test network',
          body: [
            'Records are anchored on the Polygon Amoy test network, with no guarantee that they stay.',
          ],
        },
        {
          heading: 'Fair use',
          body: [
            'Do not try to break, overload or scrape the service, and do not share codes that are not yours. Reports about a passport must be honest.',
          ],
        },
        {
          heading: 'Changes',
          body: [
            'The service, these terms and the data may change or be removed without notice.',
          ],
        },
        {
          heading: 'Liability',
          body: [
            'As far as the law allows, the team is not liable for any loss from using the demo.',
          ],
        },
      ],
    },
  },
}

const ka: TrustCopy = {
  disclaimer:
    'ეს არ არის BTU-ის ოფიციალური სერვისი. ეს სტუდენტური ჰაკათონის პროექტია და დემოს სახით არის ნაჩვენები.',
  projectLine:
    'BTU AI უნარების ციფრული პასპორტი · სტუდენტური ჰაკათონის პროექტი',
  team: TEAM_KA.join(' · '),
  teamLabel: 'გუნდი',
  footerLabel: 'ამ პროექტის შესახებ',
  testnetNote:
    'დაფიქსირებულია Polygon Amoy სატესტო ქსელში. ეს დემოა: სატესტო ქსელის ჩანაწერების შენარჩუნება გარანტირებული არ არის.',
  navAbout: 'შესახებ',
  navPrivacy: 'კონფიდენციალურობა',
  navTerms: 'პირობები',
  navGithub: 'GitHub',
  backHome: 'მთავარ გვერდზე დაბრუნება',
  notFoundTitle: 'გვერდი ვერ მოიძებნა',
  notFoundBody: 'ეს გვერდი არ არსებობს ან გადატანილია.',
  errorTitle: 'რაღაც არ გამოვიდა',
  errorBody:
    'მოულოდნელი შეცდომა მოხდა. სცადეთ ხელახლა ან დაბრუნდით მთავარ გვერდზე.',
  tryAgain: 'ხელახლა ცდა',
  removalWithEmail:
    'მონაცემების გასასწორებლად ან წასაშლელად მოგვწერეთ: {email}. პასპორტს ბაზიდან და Sheet-იდან წავშლით. ბლოკჩეინზე უკვე ჩაწერილი ჰეშები დარჩება.',
  removalWithoutEmail:
    'მონაცემების გასასწორებლად ან წასაშლელად მიმართეთ გუნდის წევრებს, რომელთა სახელებიც მითითებულია „შესახებ“ გვერდზე. პასპორტს ბაზიდან და Sheet-იდან წავშლით. ბლოკჩეინზე უკვე ჩაწერილი ჰეშები დარჩება.',
  pages: {
    about: {
      title: 'ამ პროექტის შესახებ',
      intro:
        'BTU AI უნარების ციფრული პასპორტი სტუდენტების მიერ შექმნილი ჰაკათონის პროექტია. ეს დემოა და არა BTU-ის ოფიციალური სერვისი.',
      sections: [
        {
          heading: 'რა არის პასპორტი',
          body: [
            'პასპორტი არის ჩანაწერი AI უნარებზე, რომლებიც სტუდენტს მიენიჭა. უნარების დამატებისას გაიცემა ახალი დანომრილი ვერსია. ყველა ვერსიას აქვს საკუთარი გადამოწმების კოდი და მისი გადმოწერა შესაძლებელია PDF-ის სახით ინგლისურად ან ქართულად. პასპორტის ID ყველა ვერსიაზე უცვლელია.',
          ],
        },
        {
          heading: 'როგორ მუშაობს გადამოწმება',
          body: [
            'ნებისმიერ ადამიანს შეუძლია გადამოწმების გვერდზე კოდის შეყვანა. სერვისი პოულობს კოდს და აჩვენებს მფლობელის სახელს, ვერსიას, უნარებს და იმას, არის თუ არა ეს უახლესი ვერსია. ელფოსტა, პასპორტის ID და უფრო ახალი ვერსიის კოდი არ ჩანს. თუ უფრო ახალი ვერსია არსებობს, შედეგი ამას აჩვენებს.',
          ],
        },
        {
          heading: 'რას ადასტურებს ბლოკჩეინზე დაფიქსირება',
          body: [
            'ვერსიის გაცემისას მისი შიგთავსის ანაბეჭდი (ჰეში) იწერება საჯარო ბლოკჩეინზე. გადამოწმებულ შედეგზე არსებული ტრანზაქციის ბმულით ამ ჩანაწერის ნახვა შეგიძლიათ. დაფიქსირება აჩვენებს, რომ ზუსტად ეს შიგთავსი ამ დროს არსებობდა და მას მერე არ შეცვლილა. ბლოკჩეინზე მხოლოდ ჰეშები იწერება, სახელები, ელფოსტები და უნარები არა.',
          ],
        },
        {
          heading: 'რას არ ადასტურებს',
          body: [
            'ის არ ადასტურებს, რომ BTU-მ უნარები დაამტკიცა, რომ სტუდენტს ეს უნარები რეალურად აქვს, ან რომ კოდის გამომყენებელი პირი მფლობელია. კოდის გაზიარება ნებისმიერს შეუძლია, ვისაც ის აქვს.',
          ],
        },
        {
          heading: 'სატესტო ქსელი',
          body: [
            'ჩანაწერები ფიქსირდება Polygon Amoy სატესტო ქსელში. ეს დემოა: სატესტო ქსელის მონაცემები შეიძლება განულდეს ან გაქრეს, ამიტომ ჩანაწერის შენარჩუნება გარანტირებული არ არის.',
          ],
        },
        {
          heading: 'წყაროს კოდი',
          body: [
            'კოდი ღიაა და MIT ლიცენზიით ვრცელდება. შეგიძლიათ ნახოთ, როგორ მუშაობს გადამოწმება და ბლოკჩეინზე დაფიქსირება.',
          ],
          link: {
            label: 'github.com/Vako-Farcxa/btu-ai-passport',
            href: REPO_URL,
          },
        },
        {
          heading: 'გუნდი',
          body: [`${TEAM_KA.join(', ')}. სტუდენტური ჰაკათონის ნამუშევარი.`],
        },
      ],
    },
    privacy: {
      title: 'კონფიდენციალურობა',
      intro:
        'ეს სტუდენტური დემოა. ვინახავთ მხოლოდ იმ მონაცემებს, რომლებიც პასპორტის გასაცემად და გადასამოწმებლად არის საჭირო.',
      sections: [
        {
          heading: 'რას ვინახავთ',
          list: true,
          body: [
            'თქვენს სახელს და უნივერსიტეტის ელფოსტას.',
            'პასპორტის მონაცემებს: პასპორტის ID, მინიჭებული უნარები და მათი თარიღები, ვერსიების ნომრები, გადამოწმების კოდები და PDF ფაილები.',
            'წყარო არის გუნდის მიერ მართული Google Sheet, სადაც ასევე წერია სტუდენტის ID, პროგრამა და განათლების საფეხური.',
            'შესვლა ხდება Supabase-ის მეშვეობით. ელფოსტას პასპორტის მოსაძებნად ვიყენებთ.',
            'პასპორტთან დაკავშირებით გაგზავნილ შეტყობინებებს: თქვენს კომენტარს, მის სტატუსს და პასუხს.',
          ],
        },
        {
          heading: 'რას ხედავს გადამმოწმებელი',
          body: [
            'ნებისმიერი, ვისაც კოდი აქვს, ხედავს მფლობელის სახელს, ვერსიას, უნარებს თარიღებით და ბლოკჩეინის ტრანზაქციის ბმულს. თქვენი ელფოსტა, პასპორტის ID, სტუდენტის ID და სხვა ვერსიების კოდები არ ჩანს. შესული სტუდენტი მხოლოდ საკუთარ პასპორტს ხედავს. ადმინისტრატორები, ანუ გუნდი, ხედავენ ყველაფერს, რაც ინახება.',
          ],
        },
        {
          heading: 'ბლოკჩეინი',
          body: [
            'ბლოკჩეინზე მხოლოდ ჰეშები იწერება. პირად მონაცემებად ისინი წაკითხვადი არ არის. ბლოკჩეინის ჩანაწერის წაშლა შეუძლებელია, სატესტო ქსელშიც კი.',
          ],
        },
        {
          heading: 'ქუქი-ფაილები',
          body: [
            'ვიყენებთ ერთ ქუქის ენის დასამახსოვრებლად და Supabase-ის შესვლის სესიას. სარეკლამო ან თვალთვალის ქუქი-ფაილები არ გვაქვს.',
          ],
        },
        {
          heading: 'გასწორება და წაშლა',
          body: ['{removal}'],
        },
        {
          heading: 'რამდენ ხანს ვინახავთ',
          body: [
            'ეს დემოა. მონაცემები ინახება დემოს მუშაობის განმავლობაში და ნებისმიერ დროს შეიძლება წაიშალოს.',
          ],
        },
      ],
    },
    terms: {
      title: 'გამოყენების პირობები',
      intro: 'გთხოვთ, წაიკითხოთ საიტის გამოყენებამდე.',
      sections: [
        {
          heading: 'დემო სერვისი',
          body: [
            'ეს საიტი სტუდენტური ჰაკათონის პროექტია და დემოს სახით არის მოწოდებული. ის არ არის BTU-ის ოფიციალური სერვისი.',
          ],
        },
        {
          heading: 'გარანტიის გარეშე',
          body: [
            'სერვისი მოწოდებულია „როგორც არის“, ყოველგვარი გარანტიის გარეშე. არ ვაგარანტირებთ ხელმისაწვდომობას, სიზუსტეს ან იმას, რომ პასპორტები მუშაობას გააგრძელებს.',
          ],
        },
        {
          heading: 'არ არის ოფიციალური დოკუმენტი',
          body: [
            'გადამოწმებული შედეგი აჩვენებს მხოლოდ იმას, რაც ამ დემომ ჩაიწერა. ნუ დაეყრდნობით მას მისაღებ, დასაქმების ან სხვა ოფიციალურ გადაწყვეტილებებში. გადაამოწმეთ BTU-ში.',
          ],
        },
        {
          heading: 'სატესტო ქსელი',
          body: [
            'ჩანაწერები ფიქსირდება Polygon Amoy სატესტო ქსელში, მათი შენარჩუნების გარანტიის გარეშე.',
          ],
        },
        {
          heading: 'დასაშვები გამოყენება',
          body: [
            'ნუ შეეცდებით სერვისის გაფუჭებას, გადატვირთვას ან მონაცემების მასობრივ ამოღებას და ნუ გაავრცელებთ კოდებს, რომლებიც თქვენ არ გეკუთვნით. პასპორტთან დაკავშირებული შეტყობინებები გულწრფელი უნდა იყოს.',
          ],
        },
        {
          heading: 'ცვლილებები',
          body: [
            'სერვისი, ეს პირობები და მონაცემები შეიძლება შეიცვალოს ან წაიშალოს გაფრთხილების გარეშე.',
          ],
        },
        {
          heading: 'პასუხისმგებლობა',
          body: [
            'კანონით დაშვებულ ფარგლებში გუნდი არ აგებს პასუხს დემოს გამოყენებით გამოწვეულ ზიანზე.',
          ],
        },
      ],
    },
  },
}

export const trust: Record<Locale, TrustCopy> = { en, ka }
