import type { Locale } from '@/i18n/messages'

export const LOCALE_COOKIE = 'passport_locale'
export const LOCALES: readonly Locale[] = ['en', 'ka']

export function isLocale(value: unknown): value is Locale {
  return value === 'en' || value === 'ka'
}

/** `en` or `ka` from the stored language choice, or null when there is none. */
export function localeFromCookie(
  value: string | null | undefined,
): Locale | null {
  return isLocale(value) ? value : null
}

/**
 * The language to show for an `Accept-Language` list (the server) or the joined
 * `navigator.languages` (the browser): the first language of the list that is English or
 * Georgian, highest `q` first. Anything else, and no list at all, shows English, so a link
 * preview bot or a visitor with another language never lands on Georgian by accident.
 * Both sides use this one function so the server HTML and the browser agree.
 */
export function negotiateLocale(
  acceptLanguage: string | null | undefined,
): Locale {
  if (!acceptLanguage) return 'en'
  const ranked = acceptLanguage
    .split(',')
    .map((part, index) => {
      const [tag = '', ...params] = part.trim().split(';')
      const q = params
        .map((param) => /^\s*q\s*=\s*([\d.]+)\s*$/i.exec(param)?.[1])
        .find((value) => value !== undefined)
      const weight = q === undefined ? 1 : Number(q)
      return {
        tag: tag.trim(),
        weight: Number.isFinite(weight) ? weight : 0,
        index,
      }
    })
    .filter((entry) => entry.tag !== '' && entry.weight > 0)
    .sort((a, b) => b.weight - a.weight || a.index - b.index)
  for (const { tag } of ranked) {
    const lower = tag.toLowerCase()
    if (lower === 'ka' || lower.startsWith('ka-')) return 'ka'
    if (lower === 'en' || lower.startsWith('en-')) return 'en'
  }
  return 'en'
}

/** The language a request should be answered in: the saved choice, else the browser's list. */
export function localeForRequest(
  cookie: string | null | undefined,
  acceptLanguage: string | null | undefined,
): Locale {
  return localeFromCookie(cookie) ?? negotiateLocale(acceptLanguage)
}
