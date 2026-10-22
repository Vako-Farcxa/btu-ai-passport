# Implementation Plan: BTU AI Skills Digital Passport

**Branch**: `001-ai-skills-passport` | **Date**: 2026-10-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-ai-skills-passport/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Every BTU student gets one permanent digital passport. A scheduled GitHub Actions workflow calls `POST /internal/sync` every 15 minutes. That route reads BTU's Google Sheet, issues a new version only when that student's skill facts change, fills BTU's English and Georgian PDF designs, and anchors two fingerprints on Polygon Amoy. The API process does not run its own sync loop. Students sign in with Google through Supabase (`btu.edu.ge` only) and download their PDFs. Anyone can submit a Verification Code on a public page and get one still result: valid, outdated version, not found, or error. The Next.js app talks to the API only. No personal data is written on-chain.

## Technical Context

**Language/Version**: Frontend TypeScript (strict) on Next.js 16 App Router. Backend Python 3.12 (uv).

**Primary Dependencies**: Frontend: Next.js, React, Tailwind CSS, shadcn/ui, GSAP, Supabase Auth (`@supabase/ssr`), zod. Backend: FastAPI, pydantic-settings, gspread, pypdf, reportlab, web3.py, supabase-py, httpx, uvicorn. No new packages. Solidity 0.8.24 for the one anchor contract, compiled ahead of time so the running API does not need a compiler.

**Storage**: Supabase Postgres for passports, versions, skills, and anchors. Private Supabase Storage bucket for the English and Georgian PDFs. Google Sheet is the only source of student and skill facts.

**Testing**: Frontend `npm run check` (tsc, eslint, prettier, vitest) and `npm run e2e` (Playwright) for UI. Backend `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest`. Tests are written before the implementation they cover.

**Target Platform**: Web. Frontend on Vercel. Backend on Railway or Render. Chain is Polygon Amoy (chain id 80002), not a production network.

**Project Type**: Web application (Next.js frontend + FastAPI backend).

**Performance Goals**: A sheet change becomes one new version and both PDFs within 15 minutes of the GitHub Actions schedule. A verification request returns one outcome in well under 15 seconds (API target: under 1 second when the database is reachable, excluding the visitor opening the public transaction). One sync cycle covers a 100-student sheet.

**Constraints**: `btu.edu.ge` Google accounts only. CORS allowlist. Secrets only in backend `.env` and host env. Service-role key, sheet credentials, and the issuer private key never reach the browser. On-chain payload is two `bytes32` fingerprints. GSAP uses transform and opacity only, respects `prefers-reduced-motion`, and is not used on the verification result. English and Georgian UI. Official names and skills are not translated. Keyboard access and outcomes that do not depend on color alone.

**Scale/Scope**: Hackathon/demo cohort, about 100 students, one sheet, three screens (home, passport, verify), one anchor contract, two PDF languages.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unratified placeholder. It names no principles, so it adds no gates and records no violations.

The user required this plan to follow `AGENTS.md`. Those rules are the working gate:

| Gate | Result |
| --- | --- |
| Frontend and backend stay in `frontend/` and `backend/` with the named stack | Pass |
| Browser calls only the JSON API; Pydantic models and TypeScript types match `contracts/openapi.yaml` | Pass |
| Tests first; definition-of-done commands stay the ones in AGENTS.md | Pass |
| No new dependency; existing libraries cover sync, PDF, chain, auth, and UI | Pass |
| Secrets stay off the frontend; personal data stays off-chain | Pass |
| Loading, empty, and error states; zod and Pydantic validate input | Pass |
| Semantic HTML, keyboard use, visible focus, text alternatives | Pass |
| GSAP motion is transform/opacity, reduced-motion aware, and absent on the verify result | Pass |

**Post-design re-check**: Pass. The data model, API, sheet contract, and anchor contract keep the same boundaries. Postgres RLS blocks direct browser reads. The anchor contract stores two hashes and nothing else. i18n is a local message map, not a new library.

## Project Structure

### Documentation (this feature)

```text
specs/001-ai-skills-passport/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/           # Phase 1
│   ├── openapi.yaml
│   ├── sheet.md
│   └── PassportAnchor.sol
└── tasks.md             # Phase 2 task list
```

### Source Code (repository root)

```text
backend/
├── assets/
│   ├── templates/           # passport-en.pdf, passport-ka.pdf, fields.json
│   ├── fonts/               # Georgian-capable TTF used when drawing overflow pages
│   └── PassportAnchor.json  # ABI + bytecode, produced once from the contract
├── src/passport_api/
│   ├── main.py              # app and CORS only; no sync loop
│   ├── settings.py
│   ├── api/                 # /me/passport, pdf download, /verify, /internal/sync
│   ├── schemas.py           # Pydantic models matching openapi.yaml
│   ├── auth.py              # Supabase JWT + btu.edu.ge check
│   ├── db.py                # service-role Supabase client
│   ├── sync.py
│   ├── pdf.py
│   └── chain.py
├── scripts/deploy_anchor.py
├── scripts/seed_demo.py     # fixed verify fixtures, no sheet and no chain required
└── tests/

frontend/
├── src/app/
│   ├── layout.tsx           # lang, fonts, skip link
│   ├── page.tsx             # home: sign in + link to verify
│   ├── passport/page.tsx
│   └── verify/page.tsx      # no GSAP
├── src/components/
├── src/i18n/                # en + ka messages, locale cookie
├── src/lib/api/             # fetch client, zod, types mirrored from the contract
├── src/test/
└── e2e/

supabase/migrations/         # tables, uniqueness, RLS enabled with no browser policies

.github/workflows/sync.yml    # cron every 15 minutes, POST /internal/sync
```

**Structure Decision**: Use the app that already exists. The API package is `passport_api` under `backend/src`. The UI is the Next.js App Router under `frontend/src/app`. Supabase is the database, auth provider, and file store. SQL migrations live in `supabase/migrations`. The browser never queries those tables.

**Sync schedule**: `backend/src/passport_api/main.py` must not start a timer, lifespan loop, or background task that reads the sheet. `.github/workflows/sync.yml` is the only scheduler. It runs on cron `*/15 * * * *` and `workflow_dispatch`, then `POST`s `{SYNC_URL}/internal/sync` with header `X-Sync-Token` taken from the `SYNC_TOKEN` repository secret. `SYNC_URL` is a repository secret too. A second call while a sync run is `running` returns `skipped`.

## Complexity Tracking

No constitution or AGENTS.md violations need a justification. The two deployables, the sheet, and the anchor contract are the stack the product already requires.
