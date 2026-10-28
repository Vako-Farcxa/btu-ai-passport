const MAX_CODE_LENGTH = 64

/** A code from the `?code=` query value, ready for the input. Empty when blank. */
export function codeFromParam(value: string | null): string {
  if (value === null) return ''
  return value.trim().toUpperCase().slice(0, MAX_CODE_LENGTH)
}

/** Public link that opens the verify page and checks this code. */
export function shareLinkFor(origin: string, code: string): string {
  return `${origin}/verify?code=${encodeURIComponent(code.trim())}`
}
