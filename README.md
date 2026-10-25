# BTU AI Skills Digital Passport

Issues verifiable AI skills passports to BTU students. Passports come from a Google Sheet, students sign in with their btu.edu.ge account and download English or Georgian PDFs, and anyone can verify a passport by its code. Each version can be anchored on Polygon Amoy.

## Structure

- `frontend/`: Next.js app (sign-in, passport, public verify page)
- `backend/`: FastAPI service (sheet sync, PDFs, verification, Amoy anchoring)
- `supabase/`: database setup
- `specs/`: spec-kit specification, plan and tasks
- `.github/workflows/sync.yml`: runs the sheet sync every 15 minutes

## Run locally

Backend:

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

Open http://localhost:3000. Try verifying with the demo code `K9M2-N3P4-Q5R6-S7T8`.

## Checks

- Backend: `uv run ruff format . && uv run ruff check . && uv run mypy . && uv run pytest`
- Frontend: `npm run check` and `npm run e2e`
