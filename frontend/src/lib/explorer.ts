export const EXPLORER_HOST = 'amoy.polygonscan.com'

const TX_PATH = /^\/tx\/(0x)?[0-9a-fA-F]+$/

/**
 * Returns the link only if it is an https transaction page on the Polygon Amoy explorer,
 * otherwise null. Links come from the API, so they are checked before they are rendered:
 * a `javascript:` URL, another host, or an address with embedded credentials never
 * becomes an href.
 */
export function explorerTxUrl(value: string | null | undefined): string | null {
  if (!value) return null
  let url: URL
  try {
    url = new URL(value)
  } catch {
    return null
  }
  if (url.protocol !== 'https:') return null
  if (url.hostname !== EXPLORER_HOST || url.port !== '') return null
  if (url.username !== '' || url.password !== '') return null
  if (!TX_PATH.test(url.pathname)) return null
  return url.toString()
}

export function explorerTxUrlFor(txHash: string): string | null {
  return explorerTxUrl(
    `https://${EXPLORER_HOST}/tx/${encodeURIComponent(txHash)}`,
  )
}
