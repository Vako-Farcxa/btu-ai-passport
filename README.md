# BTU AI Skills Digital Passport

[![CI](https://github.com/Vako-Farcxa/btu-ai-passport/actions/workflows/ci.yml/badge.svg)](https://github.com/Vako-Farcxa/btu-ai-passport/actions/workflows/ci.yml)

**Live: [btu-ai-passport.vercel.app](https://btu-ai-passport.vercel.app)**

Verifiable AI skills passports for BTU students. A team keeps awards in a Google Sheet, students sign in with their btu.edu.ge account to see their passport and download English or Georgian PDFs, and anyone can check a passport with its verification code. Every version is anchored on a public blockchain, so a changed passport can be told apart from the original.

> **Disclaimer:** this is a student hackathon project. It is a demo and **not an official BTU service**.
> **Testnet:** passport versions are anchored on the **Polygon Amoy test network**. Test network data can be reset, so there is no guarantee a record stays available.

| Home | Verify result |
| --- | --- |
| ![Home](docs/screenshots/home.png) | ![Verify result](docs/screenshots/verify-result.png) |

| Student passport | Admin sign-in gate |
| --- | --- |
| ![Student passport](docs/screenshots/passport.png) | ![Admin sign-in](docs/screenshots/admin-login.png) |

The screenshots use fictional sample data (a demo student, Nino Beridze), not real students.

## Features

- Sign in with a btu.edu.ge Google account and see your own passport, version by version.
- Download each version as a PDF in English or Georgian.
- Public verification page: enter a code and see the holder name, version, skills and whether it is the latest version. It never shows email or passport ID.
- Share link per version (`/verify?code=...`).
- Blockchain anchoring on Polygon Amoy, with a public transaction link per version.
- Admin panel behind an allow-list: award skills, add students, manage the skills catalog, watch syncs and anchors, review student flags.
- Google Sheet stays the source of truth. A sync runs every 15 minutes and writes the result back to each row.
- Students can flag an issue on a version and read the admin reply.
- English and Georgian interface, About, Privacy and Terms pages.

## Architecture

```mermaid
flowchart LR
    Sheet["Google Sheet<br/>(source of truth)"] -->|every 15 min| Sync["Sync<br/>(GitHub Actions cron)"]
    Sync -->|POST /internal/sync| API["FastAPI<br/>(Render)"]
    API <-->|rows, versions, PDFs| DB[("Supabase<br/>Postgres, Auth, Storage")]
    API -->|writes status back| Sheet
    API -->|hash of each version| Chain["Polygon Amoy<br/>(test network)"]
    Web["Next.js<br/>(Vercel)"] -->|REST + Supabase JWT| API
    Web -->|Google sign-in| DB
    Student(["Student"]) --> Web
    Verifier(["Anyone with a code"]) --> Web
```

Only hashes go on the blockchain, never names, emails or skills.

## Tech stack

- **Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS 4, GSAP, zod, Vitest and Playwright
- **Backend:** Python 3.12, FastAPI, gspread, reportlab and pypdf, web3.py, pytest, ruff and mypy
- **Data and auth:** Supabase (Postgres, Google sign-in, Storage)
- **Chain:** Polygon Amoy test network
- **Hosting:** Vercel (web), Render (API), GitHub Actions (sync schedule)

## Structure

- `frontend/`: Next.js app (sign-in, passport, public verify page, admin panel)
- `backend/`: FastAPI service (sheet sync, PDFs, verification, Amoy anchoring)
- `supabase/`: database migrations
- `specs/`: spec-kit specification, plan and tasks
- `docs/screenshots/`: images used in this README
- `.github/workflows/sync.yml`: runs the sheet sync every 15 minutes
- `.github/workflows/backup.yml`: nightly encrypted backup of the database and the Sheet (`docs/RESTORE.md` explains how to restore)
- `.github/workflows/ci.yml`: tests and checks on every push and pull request (`.github/scripts/` has the migration check, `.github/dependabot.yml` the update schedule)

## Run locally

Backend (without Supabase variables it runs on demo data):

```bash
cd backend
uv run uvicorn passport_api.main:app --reload
```

Frontend:

```bash
cd frontend
cp .env.example .env.local   # fill in Supabase URL and anon key
npm install
npm run dev
```

Open http://localhost:3000. Try verifying with the demo code `K9M2-N3P4-Q5R6-S7T8` against the demo backend.

## Verify a passport yourself

Every passport version is anchored on the **Polygon Amoy test network** in the `PassportAnchor` contract:

- Contract address: [`0xf436Ba2A2cd1dc78f1543A1E7e8a9f20B2C40c32`](https://amoy.polygonscan.com/address/0xf436Ba2A2cd1dc78f1543A1E7e8a9f20B2C40c32)
- ABI: [`docs/contract/PassportAnchor.abi.json`](docs/contract/PassportAnchor.abi.json)
- Source: [`specs/001-ai-skills-passport/contracts/PassportAnchor.sol`](specs/001-ai-skills-passport/contracts/PassportAnchor.sol). Once the source is published on Polygonscan ("Verify and Publish", Solidity 0.8.26, optimizer settings of the deployment), its Read Contract tab works directly. Until then use the script below, or load the ABI in Remix ("At Address").

The contract stores one mapping, `anchors(verificationIdHash) -> contentHash`. A slot can be written once and never changed.

**What the verify page does.** For a confirmed code it recomputes the content hash from the stored name, passport ID, version and skills, compares it with the hash stored in the database, then reads the contract and compares again. Results:

| Result | Meaning |
|---|---|
| Valid / Outdated version, badge "Verified on-chain, block N" | Database and contract agree. |
| "Does not match the blockchain" (no name, no skills) | The stored passport changed, or the contract holds a different hash or none. |
| Valid, badge "On-chain check unavailable, try later" | The RPC could not be reached in 3 seconds. The database result is shown, but it is never called verified. |

**Check it without trusting this site**

1. On the verify result, open "Verify it yourself". It lists the contract address, the key and the expected fingerprint.
2. Open the contract on [Polygonscan](https://amoy.polygonscan.com/address/0xf436Ba2A2cd1dc78f1543A1E7e8a9f20B2C40c32#readContract) and go to Read Contract (or load `docs/contract/PassportAnchor.abi.json` in Remix at the same address).
3. Call `anchors` with the key. It returns the content hash. It must equal the expected fingerprint. All zeros means nothing is anchored for that code.

The key is `keccak256` of the verification code in upper case (UTF-8). The content hash is `keccak256` of this compact JSON, with keys sorted and text normalised (Unicode NFC, trimmed):

```json
{"holder_name":"...","passport_id":"BTU-...","skills":[{"awarded_on":"2025-06-01","badge":"...","skill":"..."}],"version":2}
```

Skills are sorted by skill, badge and date (a missing date last), and exact duplicates are collapsed. `awarded_on` is `null` when there is no valid date.

**Script.** To recompute the hash from a passport's facts and compare it with the contract, with no BTU server involved:

```bash
cd backend
uv run python scripts/verify_onchain.py --code ABCD-EFGH-IJKL-MNOP --passport passport.json
```

`passport.json` holds `holder_name`, `passport_id`, `version` and `skills` (`skill`, `badge`, `awarded_on`). It needs a Polygon Amoy RPC URL (a public one is the default, override with `--rpc`) and no key. Exit code 0 is verified, 1 is a mismatch or not anchored, 2 means the chain could not be read.

**Backend settings for the on-chain check** (all optional beyond the existing `AMOY_RPC_URL`):

- `AMOY_RPC_URL`: the RPC node to read from. Without it the badge always says the check is unavailable.
- `ANCHOR_CONTRACT_ADDRESS`: defaults to the published address above.
- `ONCHAIN_VERIFY` (default `true`): set `false` to turn the on-chain read off.
- `ONCHAIN_TIMEOUT_SECONDS` (default `3`): timeout of each RPC request.

Reads are cached in memory: a filled slot for 24 hours (it cannot change), an empty one for 1 minute, and after a failed read the RPC is left alone for 30 seconds. A free public RPC is therefore asked about each version about once a day.

## Google Sheet

The sync reads BTU's official test sheet layout (title rows above the header, with `BTU Email (Test)`, `Passport ID (Existing)`, `Skill Name`, `Date Earned` and so on) as well as the old `email, full_name, skill, badge, awarded_on` layout. Existing Passport IDs are kept. After each run it writes `Passport Sync Status` (`SYNCED`/`FAILED`), `Synced Passport Version` (`V1`, `V2`...), `Synced At (UTC)` and `Sync Error / Notes` back to each row. Full rules: `specs/001-ai-skills-passport/contracts/sheet.md`.

Setup: share the sheet with the service account as Editor, set `SHEET_ID` and `GOOGLE_SERVICE_ACCOUNT_JSON` in `backend/.env`, and set `ALLOWED_EMAIL_DOMAINS=btu.edu.ge,example.org` to accept the test emails. Run the files in `supabase/migrations/` in order.

## Monitoring and backups

### Health checks

- `GET /health`: the API process is alive. It touches nothing else, so it is cheap and safe to ping often.
- `GET /health/ready`: checks the database, the Google Sheet and the Amoy RPC and reports each one. `200` when the database works (overall `ok`, or `degraded` if only the Sheet or the chain is down), `503` when it does not. The answer is cached for 60 seconds, so frequent pings cannot use up the Sheets or RPC quotas, and it never shows a URL or secret.
- The admin dashboard (`/admin`) shows a red or amber banner when the last sync failed (with the reason), no sync has finished for over an hour, an anchor is stuck or gave up, or the database consistency check finds problems.

### Uptime monitoring with UptimeRobot (free)

The free plan checks every 5 minutes, which also keeps the free Render service from falling asleep (it sleeps after 15 minutes without a request).

1. Sign up at [uptimerobot.com](https://uptimerobot.com) and open the dashboard.
2. **Add New Monitor**, type **HTTP(s)**, friendly name `BTU Passport API`, URL `https://<your-api>.onrender.com/health`, interval **5 minutes**. Under **Alert contacts** tick your email. Create it. (The free plan checks with HEAD, which `/health` answers.)
3. Optional, to also hear about a broken Sheet or chain: **Add New Monitor**, type **Keyword**, URL `https://<your-api>.onrender.com/health/ready`, keyword `degraded`, **Alert when: keyword exists**, interval 5 minutes, same email. This one also goes red on its own when the database is down, because `/health/ready` then answers 503.

### Nightly backup

`.github/workflows/backup.yml` runs every night at 02:05 Tbilisi time (and on demand from the Actions tab). It saves every database table and every Sheet tab, packs them into one file, **encrypts it with AES-256**, and keeps it as a workflow artifact for 30 days. The repository is public and signed-in GitHub users can download artifacts of a public repository, so the encryption is what keeps the data private. Add these repository secrets first (Settings, Secrets and variables, Actions, New repository secret):

| Secret | What it is |
| --- | --- |
| `SUPABASE_URL` | The same value as on Render (`https://xxxx.supabase.co`). |
| `SUPABASE_SERVICE_ROLE_KEY` | The same service role key as on Render. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | The same service account JSON as on Render. The backup only reads the Sheet. |
| `SHEET_ID` | The same Sheet id as on Render. |
| `BACKUP_PASSPHRASE` | A new long random passphrase (at least 16 characters). Keep a copy in your password manager: without it a backup cannot be opened, and nobody can reset it. |

Run it by hand and check it, then restore: see [`docs/RESTORE.md`](docs/RESTORE.md). If a run fails (a missing secret, the Sheet no longer shared with the service account), GitHub emails you. GitHub also switches scheduled workflows off after 60 days without any repository activity, so look at the Actions tab now and then.

## Testing

About 1,000 automated tests run on every push and pull request (GitHub Actions, `.github/workflows/ci.yml`, no secrets needed):

| Suite | Count | What it covers | Run it locally |
| --- | --- | --- | --- |
| Backend (pytest) | 676 | API, sync, verification, on-chain check, PDFs, rate limits, security headers, health checks, backup and restore, and the real migrations plus sync function on a real Postgres (pgserver) | `cd backend && uv run pytest` |
| Frontend unit (Vitest) | 300 | validation, formatting, headers policy, helpers, components | `cd frontend && npm test` |
| End-to-end (Playwright, Chromium) | 43 | verify page and on-chain badge, English and Georgian, passport page, share links, keyboard use, reduced motion, security headers, rate-limit message, admin health banner | `cd frontend && npm run e2e` |

The CI jobs, with the check names GitHub shows:

- **Backend:** `ruff format --check`, `ruff check`, `mypy` (strict) and `pytest`.
- **Frontend:** `tsc`, ESLint, Prettier, Vitest and a production `next build` that must have an https API address.
- **E2E (Playwright):** the specs against the production build, with every API call mocked in the browser.
- **Migrations:** every file in `supabase/migrations` applied in order to an empty Postgres 17, and the newest one applied twice.
- **Secret scan:** gitleaks over the full history, fails on any leaked key.

Dependabot opens weekly pull requests for Python, npm and GitHub Actions updates (minor and patch updates are grouped).

Before opening a pull request, run the same checks locally:

- Backend: `uv run ruff format . && uv run ruff check . && uv run mypy . && uv run pytest`
- Frontend: `npm run check` and `npm run e2e`

## Team

Vako Partskhaladze, Tazo Futuridze, Giorgi Gvianishvili.

Source: https://github.com/Vako-Farcxa/btu-ai-passport

## License

[MIT](LICENSE), copyright 2026 Vako Partskhaladze, Tazo Futuridze, Giorgi Gvianishvili.
