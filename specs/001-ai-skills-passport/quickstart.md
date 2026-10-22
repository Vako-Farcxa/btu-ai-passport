# Quickstart: BTU AI Skills Digital Passport

Validation guide for [spec.md](./spec.md). Implementation detail belongs in the later task list. Shapes are defined in [data-model.md](./data-model.md), [contracts/openapi.yaml](./contracts/openapi.yaml), [contracts/sheet.md](./contracts/sheet.md), and [contracts/PassportAnchor.sol](./contracts/PassportAnchor.sol).

## Prerequisites

- Node.js and npm, Python 3.12, and uv.
- A Supabase project with Google auth enabled, the Postgres migration applied, and a private `passports` bucket.
- A Google service account that can read the sheet described in the sheet contract.
- BTU PDF templates at `backend/assets/templates/passport-en.pdf` and `passport-ka.pdf`, plus `fields.json`.
- A Polygon Amoy wallet with test funds. That wallet deploys `PassportAnchor` and is the only issuer. The API loads `backend/assets/PassportAnchor.json`.
- Backend `.env` (not committed): Supabase URL and service-role key, sheet id and service-account credentials, `AMOY_RPC_URL`, anchor contract address, issuer private key, `SYNC_TOKEN`, and `CORS_ORIGINS`.
- Frontend `.env`: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`. No service-role key, sheet secret, or issuer key.

## Run

```bash
cd backend && uv run uvicorn passport_api.main:app --reload
cd frontend && npm run dev
```

The API listens on port 8000. The app listens on port 3000. CORS allows that origin.

## Checks

Backend, from `backend/`:

```bash
uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest
```

Frontend, from `frontend/`:

```bash
npm run check
npm run e2e
```

Unit tests cover canonical hashing, code normalization, sync idempotency against a fake sheet, the four verify outcomes, and the domain check. End-to-end tests cover sign-in rejection, the empty passport, both languages, and the verify page. The verify result must not animate.

## Scenarios

1. **First issue.** Put one new `btu.edu.ge` student with two skills on the sheet. Trigger `POST /internal/sync` with `X-Sync-Token`, or wait for `.github/workflows/sync.yml` (every 15 minutes). The API does not poll on its own. Expect one passport id, version 1, both PDFs, and one Amoy transaction. The transaction input contains the two fingerprints from the data model and no name or skill text.
2. **Unchanged read.** Sync again. Expect `versions_created: 0` and the same transaction.
3. **Skill change.** Add, remove, or edit a skill or award date. Sync once. Expect version 2 only, a new pair of PDFs, a new code, and a new transaction. The passport id stays the same. Several edits before the sync still produce one version.
4. **Name only.** Change `full_name` and sync. Expect no new version. Version 1's PDF still shows the issued name.
5. **Student.** Sign in with the matching `btu.edu.ge` account. Expect the passport, history, and code. Download `en` and `ka`. Switch language and expect the labels to change while skill text stays as written on the sheet. A non-BTU Google account receives `domain_not_allowed` and no passport. A BTU account missing from the sheet sees the empty state.
6. **Employer.** On `/verify`, without signing in, submit the current code and expect `valid`, the issued name, skills, dates, version, latest, and the transaction link. Submit version 1's code and expect `outdated` for that older list and that older transaction. Submit an unknown code and expect `not_found` with no name or skills. Submit an empty field and expect a prompt, not `not_found`. Stop the database or use a version whose anchor is not `confirmed` and expect `error`, not valid or outdated. Repeat the found and missing cases in Georgian. The result text stays still.
7. **Keyboard and reduced motion.** Complete sign-in and verify with the keyboard only. With reduced motion requested, home and passport do not play the entrance, and verify never imports an animation.
