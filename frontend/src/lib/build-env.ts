type Env = Record<string, string | undefined>

/**
 * Stops a production build whose API address is missing or not https. Runs from
 * next.config.ts. Only a real production deploy (VERCEL_ENV=production) or a build that opts
 * in with REQUIRE_PRODUCTION_ENV=1 is checked, so local builds and tests keep working with
 * http://localhost.
 */
export function assertProductionApiUrl(env: Env): void {
  const isProductionDeploy =
    env.VERCEL_ENV === 'production' || env.REQUIRE_PRODUCTION_ENV === '1'
  if (!isProductionDeploy) return

  const value = env.NEXT_PUBLIC_API_URL?.trim()
  if (!value) {
    throw new Error(
      'NEXT_PUBLIC_API_URL is not set. Add the public https address of the API ' +
        '(for example https://your-api.onrender.com) to the Production environment ' +
        'variables, then redeploy.',
    )
  }
  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw new Error(`NEXT_PUBLIC_API_URL is not a valid URL: ${value}`)
  }
  if (url.protocol !== 'https:') {
    throw new Error(
      `NEXT_PUBLIC_API_URL must use https in production, got ${url.protocol}//${url.host}`,
    )
  }
  if (['localhost', '127.0.0.1', '[::1]', '0.0.0.0'].includes(url.hostname)) {
    throw new Error(
      'NEXT_PUBLIC_API_URL points at this machine, not at the deployed API.',
    )
  }
}
