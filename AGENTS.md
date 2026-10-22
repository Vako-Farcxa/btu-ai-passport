# AGENTS.md: BTU AI Skills Digital Passport

## Layout
- `frontend/`: Next.js (App Router, TypeScript strict), Tailwind, shadcn/ui, GSAP, Supabase auth. Deployed on Vercel.
- `backend/`: FastAPI (Python 3.12, uv). Google Sheets sync (gspread), PDF generation (pypdf + reportlab), Polygon Amoy anchoring (web3.py), Supabase (Postgres). Deployed on Railway/Render.
- Specs live in `specs/` (spec-kit). Follow the current spec and plan; ask before deviating.

## Workflow
- Plan before coding: short plan (goal, files touched, risks). Big changes need approval.
- Tests first, then implementation. Small, focused changes; don't refactor unrelated code.
- Simple, readable code over clever code. No new dependencies without a reason.
- Frontend talks to backend only through the API; keep request/response shapes in sync (Pydantic models <-> TS types).

## Definition of done (run, fix every error, then report what you ran)
- Frontend (`cd frontend`): `npm run check` (types, lint, format, unit tests); `npm run e2e` for UI changes, and click through it with the Playwright MCP.
- Backend (`cd backend`): `uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest`.
- Never claim something works without running it.

## Quality bar
- Handle loading, empty and error states. Validate all input (zod / Pydantic).
- Secrets only in `.env` files, never committed, never sent to the frontend. No personal data on-chain.
- Accessible: semantic HTML, keyboard nav, visible focus, contrast, alt text.
- Animations: GSAP, transforms/opacity only, respect `prefers-reduced-motion`. Never animate the verify result.
- Before demo: Lighthouse and the security review skills; fix anything red.

## Token use
- Read only the files you need; prefer `@file` context over repo-wide scans.
- Short replies: diffs and results, not essays. One feature per chat.
