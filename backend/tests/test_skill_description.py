from dataclasses import replace
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from passport_api.api import verify as verify_api
from passport_api.demo_data import DEMO_VERSIONS
from passport_api.fingerprint import content_hash, skill_fingerprint
from passport_api.main import app
from passport_api.pdf import PassportPdf, render_pdf
from passport_api.schemas import Skill
from passport_api.settings import settings
from passport_api.store import MemoryStore
from passport_api.sync import FakeSheet, MemorySyncStore, records_from_values, run_sync

FIXTURE = Path(__file__).parent / "fixtures" / "official_test_data.xlsx"
DESCRIPTION = "Explains how modern AI tools work and where they fail."


def _official() -> tuple[list[str], list[dict[str, object]]]:
    sheet = openpyxl.load_workbook(FIXTURE).worksheets[0]
    grid: list[list[object]] = [
        ["" if c is None else c for c in row] for row in sheet.iter_rows(values_only=True)
    ]
    return records_from_values(grid)


@pytest.fixture
def test_domains(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "allowed_email_domains", "btu.edu.ge, example.org")


@pytest.mark.usefixtures("test_domains")
def test_official_sheet_description_is_stored_on_skills() -> None:
    _, records = _official()
    store = MemorySyncStore()
    run_sync(store, FakeSheet([{k: str(v) for k, v in r.items()} for r in records]))
    expected = {
        (str(r["BTU Email (Test)"]).lower(), str(r["Skill Name"]).strip()): str(
            r["Skill Description"]
        ).strip()
        for r in records
        if str(r["BTU Email (Test)"]).strip() and str(r["Skill Description"]).strip()
    }
    assert expected
    stored = {(v.email, s.skill): s.description for v in store.versions for s in v.skills}
    for key, text in expected.items():
        assert stored[key] == text


def test_description_does_not_change_fingerprint_or_content_hash() -> None:
    plain = (Skill(skill="Python", badge="BDG-AI-001", awarded_on="2025-01-15"),)
    described = (plain[0].model_copy(update={"description": DESCRIPTION}),)
    assert skill_fingerprint(plain) == skill_fingerprint(described)
    first = content_hash(holder_name="Ada", passport_id="BTU-X", skills=plain, version=1)
    second = content_hash(holder_name="Ada", passport_id="BTU-X", skills=described, version=1)
    assert first == second


def test_description_only_edit_creates_no_new_version() -> None:
    store = MemorySyncStore()
    row = {"email": "ada@btu.edu.ge", "full_name": "Ada", "skill": "Python"}
    run_sync(store, FakeSheet([row]))
    run_sync(store, FakeSheet([{**row, "Skill Description": DESCRIPTION}]))
    assert len(store.versions) == 1


def test_verify_returns_description(monkeypatch: pytest.MonkeyPatch) -> None:
    current = DEMO_VERSIONS[1] if DEMO_VERSIONS[1].version > 1 else DEMO_VERSIONS[0]
    skill = current.skills[0].model_copy(update={"description": DESCRIPTION})
    versions = [v for v in DEMO_VERSIONS if v is not current]
    versions.append(replace(current, skills=(skill,)))
    monkeypatch.setattr(verify_api, "get_store", lambda: MemoryStore(versions))
    response = TestClient(app).post("/verify", json={"code": current.verification_code})
    body = response.json()
    assert body["outcome"] in {"valid", "outdated"}
    assert body["skills"][0]["description"] == DESCRIPTION


def test_pdf_lists_descriptions_in_both_languages() -> None:
    document = PassportPdf(
        holder_name="Ada",
        passport_id="BTU-X",
        version=1,
        issued_on="2026-01-01",
        verification_code="AAAA-BBBB-CCCC-DDDD",
        skills=(
            Skill(skill="Python", badge="BDG-AI-001", awarded_on=None, description=DESCRIPTION),
        ),
    )
    for lang in ("en", "ka"):
        pdf = render_pdf(lang, document)
        text = " ".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages)
        assert "modern AI tools" in " ".join(text.split())
