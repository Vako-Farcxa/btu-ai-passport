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
            'When you check a code, this site recomputes the fingerprint from the stored passport and reads the one recorded on the blockchain. It says "Verified on-chain" only if they match, and it says so plainly when the blockchain could not be reached. You can repeat the check yourself on Polygonscan, using the "Verify it yourself" section of a result.',
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
        'What this site shows, what it stores, where it is stored, and who to ask about it.',
      sections: [
        {
          heading: 'What the site shows',
          body: [
            'The public verify page shows, for a verification code, the holder name, the passport version, the skills with their dates and a link to the blockchain transaction. It never shows an email address, a passport ID, a student ID or the codes of other versions.',
            'A signed-in student sees only their own passport. The admin team can see everything that is stored.',
          ],
        },
        {
          heading: 'Where the data comes from',
          body: [
            'Names, skills and verification codes come from the BTU test sheet, a Google Sheet kept by the project team. It also holds a student ID, program and education level, which are never shown publicly.',
            'The people, emails and awards in that sheet are fictional demonstration data, not records of real students.',
          ],
        },
        {
          heading: 'Signing in with Google',
          body: [
            'Signing in uses Google. The site reads only your email address and your name, to check that you may sign in and to find your passport. It does not receive your Google password and does not read your mail, files or contacts.',
          ],
        },
        {
          heading: 'Where it is stored',
          list: true,
          body: [
            'Supabase stores the database (students, passports, versions, verification codes, reports and the admin activity log), the sign-in accounts and the PDF files.',
            'The API runs on Render and the web pages on Vercel. They process requests but do not keep their own copy of the data.',
            'Reports you send about a passport are stored with your comment, its status and any reply.',
          ],
        },
        {
          heading: 'Blockchain',
          body: [
            'For each passport version, a hash (a fingerprint) is written to the public Polygon Amoy test network. A hash contains no name, email, skill or any other personal data and cannot be turned back into them. A blockchain record cannot be deleted.',
          ],
        },
        {
          heading: 'Cookies, tracking and ads',
          body: [
            'The site sets one cookie to remember your language and keeps the Supabase sign-in session. There is no analytics, no advertising and no tracking, and nothing is sold or shared for marketing.',
          ],
        },
        {
          heading: 'Contact, correction and removal',
          body: [
            'To ask what is stored about you, or to have your data corrected or removed, write to vpartskhaladze@gmail.com. Your passport will be removed from the database and the Sheet. The hashes already on the blockchain stay, and they contain no personal data.',
          ],
          link: {
            label: 'vpartskhaladze@gmail.com',
            href: 'mailto:vpartskhaladze@gmail.com',
          },
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
            'კოდის შემოწმებისას ეს საიტი შენახული პასპორტიდან თავიდან ითვლის ანაბეჭდს და კითხულობს ბლოკჩეინზე ჩაწერილს. წარწერას „დადასტურებულია ბლოკჩეინზე“ მხოლოდ მაშინ აჩვენებს, თუ ისინი ემთხვევა, ხოლო თუ ბლოკჩეინთან დაკავშირება ვერ მოხერხდა, ამას პირდაპირ წერს. შემოწმების გამეორება თავადაც შეგიძლიათ Polygonscan-ზე, შედეგის განყოფილებით „თავად შეამოწმეთ“.',
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
        'რას აჩვენებს ეს საიტი, რას ინახავს, სად ინახება და ვის მივმართოთ კითხვებით.',
      sections: [
        {
          heading: 'რას აჩვენებს საიტი',
          body: [
            'საჯარო გადამოწმების გვერდი კოდის მიხედვით აჩვენებს მფლობელის სახელს, პასპორტის ვერსიას, უნარებს თარიღებით და ბლოკჩეინის ტრანზაქციის ბმულს. ის არასდროს აჩვენებს ელფოსტას, პასპორტის ID-ს, სტუდენტის ID-ს ან სხვა ვერსიების კოდებს.',
            'შესული სტუდენტი მხოლოდ საკუთარ პასპორტს ხედავს. ადმინისტრატორთა გუნდს შეუძლია ნახოს ყველაფერი, რაც ინახება.',
          ],
        },
        {
          heading: 'საიდან მოდის მონაცემები',
          body: [
            'სახელები, უნარები და გადამოწმების კოდები მოდის BTU-ის სატესტო ცხრილიდან, რომელსაც პროექტის გუნდი მართავს Google Sheet-ში. იქ ასევე წერია სტუდენტის ID, პროგრამა და განათლების საფეხური, რომლებიც საჯაროდ არასდროს ჩანს.',
            'ამ ცხრილში მოცემული ადამიანები, ელფოსტები და მინიჭებული უნარები გამოგონილი საჩვენებელი მონაცემებია და არა რეალური სტუდენტების ჩანაწერები.',
          ],
        },
        {
          heading: 'Google-ით შესვლა',
          body: [
            'შესვლა ხდება Google-ის მეშვეობით. საიტი კითხულობს მხოლოდ თქვენს ელფოსტას და სახელს, რათა შეამოწმოს, შეგიძლიათ თუ არა შესვლა, და იპოვოს თქვენი პასპორტი. ის არ იღებს თქვენს Google პაროლს და არ კითხულობს თქვენს წერილებს, ფაილებს ან კონტაქტებს.',
          ],
        },
        {
          heading: 'სად ინახება',
          list: true,
          body: [
            'Supabase ინახავს ბაზას (სტუდენტები, პასპორტები, ვერსიები, გადამოწმების კოდები, შეტყობინებები და ადმინისტრატორების აქტივობის ჟურნალი), შესვლის ანგარიშებს და PDF ფაილებს.',
            'API მუშაობს Render-ზე, ვებგვერდები კი Vercel-ზე. ისინი ამუშავებენ მოთხოვნებს, მაგრამ მონაცემების საკუთარ ასლს არ ინახავენ.',
            'პასპორტთან დაკავშირებით გაგზავნილი შეტყობინებები ინახება თქვენი კომენტარით, სტატუსითა და პასუხით.',
          ],
        },
        {
          heading: 'ბლოკჩეინი',
          body: [
            'პასპორტის თითოეული ვერსიისთვის საჯარო Polygon Amoy სატესტო ქსელში იწერება ჰეში (თითის ანაბეჭდი). ჰეში არ შეიცავს სახელს, ელფოსტას, უნარებს ან სხვა პირად მონაცემებს და მისგან მათი აღდგენა შეუძლებელია. ბლოკჩეინის ჩანაწერის წაშლა შეუძლებელია.',
          ],
        },
        {
          heading: 'ქუქი-ფაილები, თვალთვალი და რეკლამა',
          body: [
            'საიტი ადგენს ერთ ქუქის ენის დასამახსოვრებლად და ინახავს Supabase-ის შესვლის სესიას. არ გვაქვს ანალიტიკა, რეკლამა ან თვალთვალი და არაფერი იყიდება ან გადაეცემა მარკეტინგისთვის.',
          ],
        },
        {
          heading: 'კონტაქტი, გასწორება და წაშლა',
          body: [
            'იმის გასაგებად, რა ინახება თქვენ შესახებ, ან მონაცემების გასასწორებლად ან წასაშლელად მოგვწერეთ: vpartskhaladze@gmail.com. თქვენს პასპორტს ბაზიდან და Sheet-იდან წავშლით. ბლოკჩეინზე უკვე ჩაწერილი ჰეშები დარჩება და ისინი პირად მონაცემებს არ შეიცავს.',
          ],
          link: {
            label: 'vpartskhaladze@gmail.com',
            href: 'mailto:vpartskhaladze@gmail.com',
          },
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
