import { Noto_Sans_Georgian, Noto_Serif_Georgian } from 'next/font/google'

export const sans = Noto_Sans_Georgian({
  subsets: ['latin', 'georgian'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-sans-geo',
  display: 'swap',
})

export const serif = Noto_Serif_Georgian({
  subsets: ['latin', 'georgian'],
  weight: ['500', '600', '700'],
  variable: '--font-serif-geo',
  display: 'swap',
})
