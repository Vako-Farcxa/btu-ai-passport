# Frontend

Next.js app for the BTU AI Skills Digital Passport. See the [project README](../README.md) for what it does, the architecture and how to run everything.

```bash
cp .env.example .env.local   # Supabase URL, anon key, API URL
npm install
npm run dev                  # http://localhost:3000
npm run check                # types, lint, format, unit tests
npm run e2e                  # Playwright
```

## Security headers

`next.config.ts` sends them on every response, built in `src/lib/security-headers.ts`:
a Content-Security-Policy, `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, `X-Frame-Options: DENY`
(with `frame-ancestors 'none'` in the CSP) and `Cross-Origin-Opener-Policy: same-origin`.

- The pages are prerendered and cached, so a per-request nonce is not possible. Scripts therefore
  allow `'unsafe-inline'` (Next.js writes small inline scripts into each page) but never `eval`
  in production and never a foreign host. Fetches may only go to this site, `NEXT_PUBLIC_API_URL`
  and `NEXT_PUBLIC_SUPABASE_URL`. Both are read at build time, so a changed API address needs a
  redeploy. Google sign-in and the Polygonscan links are plain navigations and need no entry.
- If a policy ever breaks the live site, set `CSP_REPORT_ONLY=1` in Vercel and redeploy. The
  browser then only logs violations in the console and blocks nothing.
- `e2e/security-headers.spec.ts` checks the headers, that no page logs a CSP violation, and the
  friendly message after a 429 from the API.
