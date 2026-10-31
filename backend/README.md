# BTU AI Skills Digital Passport - Backend

FastAPI service powering the BTU AI Skills Digital Passport: Google Sheet synchronization, versioned passport issuance, verification codes, Polygon Amoy hash anchoring, and bilingual PDF generation.

## Setup

Requires Python >= 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
cd backend
cp .env.example .env
uv sync
```

## Run Locally

```bash
uv run uvicorn passport_api.main:app --reload
```

The API runs on `http://localhost:8000`. Health checks: `GET /health` (alive, touches nothing) and `GET /health/ready` (database, Sheet and chain). See "Health checks" below.

The interactive API docs (`/docs`, `/redoc`, `/openapi.json`) are off by default so a deployed API does not publish its route map. To use them locally, put `ENABLE_API_DOCS=true` in `backend/.env`.

## Blockchain anchoring

Each passport version is anchored with one transaction to the PassportAnchor contract. The
reconciler (`src/passport_api/anchoring.py`) keeps that reliable:

- It runs after every sync, from `POST /internal/anchors/reconcile` (same `X-Sync-Token` as the
  sync, called by the second job in `.github/workflows/sync.yml`), and from the admin
  "Retry anchoring" button.
- It checks the receipt of every transaction sent for a version and reads the contract slot
  before it ever sends, so the same hash is never anchored twice.
- A transaction stuck in the mempool for 10 minutes is replaced with the same nonce and a gas
  price 25 percent higher. One the node has forgotten for 3 minutes is sent again.
- Failed sends back off (2, 4, 8 ... up to 60 minutes). After 6 counted attempts a version
  becomes `failed_permanent` and waits for an admin. An unreachable RPC, an empty wallet or a
  gas spike back off without using up attempts.
- Statuses: `pending`, `retrying`, `confirmed`, `failed_permanent`. The public verify page shows
  every unconfirmed one as "Pending on-chain confirmation".
- Needs migration `supabase/migrations/0010_anchor_reliability.sql`. No new environment
  variables.

## Rate limits and security headers

Light, free, in memory (Render's free plan is one process, a restart resets the counts).
`src/passport_api/ratelimit.py`, one-minute sliding window, nothing is stored anywhere:

| Route | Limit | Counted per |
| --- | --- | --- |
| `POST /verify` | 30 a minute | visitor IP |
| `POST /flags` | 5 a minute (the hourly cap of 5 stays) | signed-in student |
| admin `POST`, `PATCH`, `DELETE` (reads are free) | 30 a minute | admin email |
| `/internal/*` | none, they need the sync token | n/a |

Over the limit the API answers `429 {"code": "rate_limited"}` with a `Retry-After` header
(whole seconds). CORS exposes `Retry-After`, and the frontend shows a friendly English or Georgian
message with the wait. Change a limit with the env vars in `.env.example`, `0` turns one off,
`RATE_LIMIT_ENABLED=false` turns all off.

**Client IP behind Render.** Render puts Cloudflare and its own proxies in front of the app.
When `TRUSTED_PROXY_HOPS` is above 0 the visitor is read from `CF-Connecting-IP` (then
`True-Client-IP`), which Cloudflare sets itself and overwrites if a visitor sends one. Counting
entries in `X-Forwarded-For` from the right is only the fallback: the chain is longer than
expected on Render, so that count landed on a Cloudflare edge address that changes per
connection, and the 30 a minute limit was never reached. Locally it is 0 and every forwarding
header is ignored. On Render keep it at 3 (`render.yaml`). IPv6
visitors are counted per /64.

Every response also carries `X-Content-Type-Options`, `Strict-Transport-Security`,
`Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy` and a `default-src 'none'` CSP
(`security_headers.py`; the CSP is skipped on `/docs` when docs are on). CORS only allows the
origins in `CORS_ORIGINS`, the methods GET, POST, PATCH, DELETE and the headers `Authorization`
and `Content-Type`, without credentials.

## On-chain verify

`POST /verify` does not trust the database alone. For a confirmed code it (1) recomputes the
content hash from the stored name, passport ID, version and skills (`fingerprint.py`) and
compares it with `passport_versions.content_hash`, then (2) reads `anchors(keccak(code))` from
the contract (`onchain.py`, read-only, no key) and compares again.

- Match: `valid` or `outdated`, with `onchain.status = "verified"`, the block number of the
  anchor transaction and the data for a Polygonscan self-check.
- Stored fields changed, or the contract holds another hash (or nothing, after a 2 minute grace
  for lagging nodes): outcome `tampered`, with no name and no skills, and an error log line.
- RPC unreachable or no `AMOY_RPC_URL`: the database result with `onchain.status =
  "unavailable"`. It is never reported as verified.
- Revoked, pending and not found are decided before any chain call and are unchanged.
- Each RPC request times out after `ONCHAIN_TIMEOUT_SECONDS` (3) with no retries. A filled slot
  is cached 24 hours (it is immutable), an empty one 1 minute, and after a failure the RPC is
  skipped for 30 seconds. `ONCHAIN_VERIFY=false` switches the read off.
- `scripts/verify_onchain.py` repeats the check from a passport's facts with no BTU server.
  Needs no migration.

## Health checks

- `GET /health` answers `{"status":"ok"}` and touches no dependency, so it is always cheap. Render's health check and the uptime monitor use it. `HEAD` works too.
- `GET /health/ready` checks the three things the app depends on and reports each as `ok`, `down` (with a short `reason` such as `timeout`, `unreachable` or `http_401`) or `not_configured`:
  - `database`: one tiny read through Supabase's REST API,
  - `sheet`: opens the Google spreadsheet,
  - `chain`: asks the Amoy RPC for the latest block.

  The answer is `200` while the database works (overall `ok`, or `degraded` when only the Sheet or the chain is down) and `503` when it does not (overall `down`). Each check has a timeout (`HEALTH_TIMEOUT_SECONDS`, default 4) and the three run side by side. The result is cached for 60 seconds (15 when something is down), so pinging it every few minutes cannot burn the Google Sheets quota or a free RPC's limit. The body holds only fixed words, never a URL, key or error message. Neither route is rate limited.
- `GET /admin/health` (admin only) feeds the red or amber banner on the admin dashboard: the last sync failed (with its reason code), no sync has completed for over 60 minutes (red after 3 hours), an anchor is `failed_permanent` or has waited over 60 minutes, or the consistency check (`sync_inconsistencies()`) found problems. Read only.

## Backups

`scripts/backup.py` exports every table (`passport_api/backup.py` lists them) to JSON Lines and every Sheet tab to CSV; `scripts/restore_backup.py` puts them back (dry run unless `--yes`). The nightly GitHub Actions workflow `backup.yml` runs the export and encrypts the result. Details and restore steps: [`docs/RESTORE.md`](../docs/RESTORE.md). A test fails if a migration adds a table that the backup does not list.

## Atomic sync

Each student's sync is one unit: the student row (or rename), the new passport version, its
skill snapshot and the source records. The backend sends the unit to the Postgres function
`sync_student_unit()` (migration `0011_atomic_sync.sql`) with one Supabase RPC call, so it
commits as one transaction or not at all. A crash can no longer leave a student without a
version, or a version whose stored skills differ from the hash that gets anchored.

- The hashes are computed from exactly the skills that are sent. The function returns the stored
  snapshot and the sync hashes it again; a mismatch fails that row with `snapshot_mismatch`.
- A retry of a unit that already committed changes nothing. A unit built on old data (another
  sync or an admin changed the student meanwhile) is refused with `sync_stale` and is retried by
  the next run.
- Anchoring still runs after the commit (the reconciler), and the Sheet write-back after that.
  Both can fail without losing data; the next run repeats them with the same values.
- A student row that has no version (left by the old sync) is healed: the next sync gives it
  version 1 instead of failing with `student_conflict`.
- The reconciler refuses to anchor a version whose stored skills do not hash to its
  `content_hash` (it becomes `failed_permanent` with `snapshot_mismatch`).
- Report damage left by the old sync, without changing anything: run
  `select * from sync_inconsistencies();` in the Supabase SQL editor (structure only), or
  `uv run python scripts/check_consistency.py`, or `GET /admin/consistency` as an admin (both
  also recompute the hashes).
- The SQL tests (`tests/test_sync_postgres.py`) run against a throwaway Postgres started by the
  `pgserver` dev dependency.

## Quality Checks & Tests

Run all checks as defined in `AGENTS.md`:

```bash
uv run ruff format . && uv run ruff check . && uv run mypy . && uv run pytest
```

