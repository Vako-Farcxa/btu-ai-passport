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

## Quality Checks & Tests

Run all checks as defined in `AGENTS.md`:

```bash
uv run ruff format . && uv run ruff check . && uv run mypy . && uv run pytest
```

