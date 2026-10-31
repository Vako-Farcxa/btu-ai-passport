export const EXPLORER_HOST = 'amoy.polygonscan.com'

const ADDRESS_PATH = /^\/address\/0x[0-9a-fA-F]{40}$/
const TX_PATH = /^\/tx\/(0x)?[0-9a-fA-F]+$/

/**
 * Returns the link only if it is an https transaction page on the Polygon Amoy explorer,
 * otherwise null. Links come from the API, so they are checked before they are rendered:
 * a `javascript:` URL, another host, or an address with embedded credentials never
 * becomes an href.
 */
export function explorerTxUrl(value: string | null | undefined): string | null {
  return explorerUrl(value, TX_PATH, false)
}

/** Same checks for the contract page (`/address/0x...`), where `#readContract` is allowed. */
export function explorerContractUrl(
  value: string | null | undefined,
): string | null {
  return explorerUrl(value, ADDRESS_PATH, true)
}

/** Block page link built from a number, never from API text. */
export function explorerBlockUrl(block: number): string | null {
  if (!Number.isSafeInteger(block) || block <= 0) return null
  return `https://${EXPLORER_HOST}/block/${block}`
}

function explorerUrl(
  value: string | null | undefined,
  path: RegExp,
  allowReadContract: boolean,
): string | null {
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
  if (!path.test(url.pathname)) return null
  if (url.search !== '') return null
  if (url.hash !== '' && !(allowReadContract && url.hash === '#readContract')) {
    return null
  }
  return url.toString()
}

export function explorerTxUrlFor(txHash: string): string | null {
  return explorerTxUrl(
    `https://${EXPLORER_HOST}/tx/${encodeURIComponent(txHash)}`,
  )
}
