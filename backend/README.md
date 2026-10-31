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

The API runs on `http://localhost:8000`. Health check endpoint: `GET /health`.

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

## Quality Checks & Tests

Run all checks as defined in `AGENTS.md`:

```bash
uv run ruff format . && uv run ruff check . && uv run mypy . && uv run pytest
```

