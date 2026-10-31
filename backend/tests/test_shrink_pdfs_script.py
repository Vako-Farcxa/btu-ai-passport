"""scripts/shrink_stored_pdfs.py: dry run changes nothing, --apply replaces only bigger files."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from passport_api.pdf import LocalPdfStorage, PassportPdf, render_pdf
from passport_api.schemas import Skill
from passport_api.store import StoredVersion

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "shrink_stored_pdfs.py"
SKILLS = (Skill(skill="Python", badge="Stamp", awarded_on="2025-06-01"),)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("shrink_stored_pdfs", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Store:
    def __init__(self, version: StoredVersion) -> None:
        self._version = version

    def versions_for_email(self, email: str) -> tuple[StoredVersion, ...]:
        return (self._version,)


def _version(en: str | None, ka: str | None) -> StoredVersion:
    return StoredVersion(
        email="ada@btu.edu.ge",
        passport_id="BTU-A1B2C3D4E5",
        full_name="Ada Lovelace",
        version=1,
        holder_name="Ada Lovelace",
        verification_code="A1B2-C3D4-E5F6-G7H8",
        issued_at="2026-02-02T10:00:00+00:00",
        skills=SKILLS,
        anchor_status="confirmed",
        tx_hash="0x" + "ab" * 32,
        pdf_en_path=en,
        pdf_ka_path=ka,
    )


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, LocalPdfStorage]:
    module = _load()
    storage = LocalPdfStorage(tmp_path)
    document = PassportPdf(
        holder_name="Ada Lovelace",
        passport_id="BTU-A1B2C3D4E5",
        version=1,
        issued_on="2026-02-02",
        verification_code="A1B2-C3D4-E5F6-G7H8",
        skills=SKILLS,
    )
    storage.put("en.pdf", render_pdf("en", document) + b"\0" * 5_000_000)  # an old, bloated file
    storage.put("ka.pdf", b"tiny")  # already smaller than anything the renderer makes
    monkeypatch.setattr(module, "get_storage", lambda: storage)
    monkeypatch.setattr(module, "SupabaseStore", lambda: _Store(_version("en.pdf", "ka.pdf")))
    monkeypatch.setattr(module, "_emails", lambda: ["ada@btu.edu.ge"])
    return module, storage


def test_a_dry_run_reports_sizes_and_changes_nothing(
    setup: tuple[ModuleType, LocalPdfStorage],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module, storage = setup
    monkeypatch.setattr(sys, "argv", ["shrink_stored_pdfs.py"])
    before = storage.get("en.pdf")
    assert module.main() == 0
    assert storage.get("en.pdf") == before
    assert "dry run" in capsys.readouterr().out


def test_apply_replaces_the_bloated_file_and_keeps_the_smaller_one(
    setup: tuple[ModuleType, LocalPdfStorage],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module, storage = setup
    monkeypatch.setattr(sys, "argv", ["shrink_stored_pdfs.py", "--apply"])
    assert module.main() == 0
    new_en: Any = storage.get("en.pdf")
    assert new_en is not None
    assert 0 < len(new_en) < 500_000
    assert new_en.startswith(b"%PDF")
    assert storage.get("ka.pdf") == b"tiny"
    assert "replaced: 1 files" in capsys.readouterr().out
