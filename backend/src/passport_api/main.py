from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from passport_api.settings import settings

app = FastAPI(title="BTU AI Skills Digital Passport API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
