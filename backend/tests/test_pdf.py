import re
import sys
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from pypdf.generic import DictionaryObject
from reportlab.pdfbase.ttfonts import TTFontFile

from passport_api.pdf import LocalPdfStorage, PassportPdf, publish_pdfs, render_pdf
from passport_api.schemas import Skill
from passport_api.settings import settings
from passport_api.sync import FakeSheet, MemorySyncStore, run_sync

ASSETS = Path(__file__).resolve().parents[1] / "assets"
FONT = ASSETS / "fonts" / "NotoSansGeorgian-Regular.ttf"
FIELDS = ASSETS / "templates" / "fields.json"

HOLDER = "ნინო ბერიძე"
OVERFLOW_SKILL = "ხელოვნური ინტელექტი"
ENGLISH_SKILL = "Machine Learning"


def _document() -> PassportPdf:
    return PassportPdf(
        holder_name=HOLDER,
        passport_id="BTU-A1B2C3D4E5",
        version=3,
        issued_on="2026-02-02",
        verification_code="A1B2-C3D4-E5F6-G7H8",
        skills=(
            Skill(skill=ENGLISH_SKILL, badge="Stamp", awarded_on="2025-06-01"),
            Skill(skill="Python", badge="", awarded_on=None),
            Skill(skill=OVERFLOW_SKILL, badge="Core", awarded_on="2024-03-03"),
        ),
    )


def _field_map(template: str) -> dict[str, str]:
    import json

    payload = json.loads(FIELDS.read_text())
    raw = payload[template]
    assert isinstance(raw, dict)
    return {str(key): str(value) for key, value in raw.items()}


def _slots(field_map: dict[str, str]) -> int:
    indexes = [
        int(key.split("_")[1])
        for key in field_map
        if key.startswith("skill_") and key.endswith("_name")
    ]
    return max(indexes)


def _value(fields: dict[str, object], name: str) -> str:
    field = fields[name]
    assert isinstance(field, DictionaryObject)
    stored = field.get("/V")
    return "" if stored is None else str(stored)


def _expected(document: PassportPdf, slots: int) -> dict[str, str]:
    values = {
        "holder_name": document.holder_name,
        "passport_id": document.passport_id,
        "version": str(document.version),
        "issued_on": document.issued_on,
        "verification_code": document.verification_code,
    }
    for index in range(1, slots + 1):
        skill = document.skills[index - 1] if index <= len(document.skills) else None
        values[f"skill_{index}_name"] = "" if skill is None else skill.skill
        values[f"skill_{index}_badge"] = "" if skill is None else skill.badge
        awarded = "" if skill is None or skill.awarded_on is None else skill.awarded_on
        values[f"skill_{index}_date"] = awarded
    return values


def test_fill_uses_canonical_fields_and_appends_overflow() -> None:
    document = _document()
    for template in ("passport-en.pdf", "passport-ka.pdf"):
        lang = "en" if template.startswith("passport-en") else "ka"
        reader = PdfReader(BytesIO(render_pdf(lang, document)))
        field_map = _field_map(template)
        slots = _slots(field_map)
        assert slots == 2
        fields = reader.get_fields()
        assert fields is not None
        expected = _expected(document, slots)
        for canonical, acro_name in field_map.items():
            assert _value(fields, acro_name) == expected[canonical]
        joined = " ".join(str(item.get("/V")) for item in fields.values())
        assert OVERFLOW_SKILL not in joined
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        assert ENGLISH_SKILL in text
        assert OVERFLOW_SKILL in text
        assert HOLDER in text
        assert len(reader.pages) >= 2
        assert "Artificial Intelligence" not in text


def test_georgian_text_is_drawn_with_the_asset_font() -> None:
    document = _document()
    pdf = render_pdf("ka", document)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
    assert HOLDER in text
    assert OVERFLOW_SKILL in text
    assert ENGLISH_SKILL in text
    _assert_embedded_font_draws(pdf, HOLDER + OVERFLOW_SKILL)


def test_republish_overwrites_the_same_storage_paths(tmp_path: Path) -> None:
    document = _document()
    storage = LocalPdfStorage(tmp_path)
    first = publish_pdfs(document, storage)
    storage.put(first[0], b"stale-en")
    storage.put(first[1], b"stale-ka")
    second = publish_pdfs(document, storage)
    passport = document.passport_id
    assert (
        first
        == second
        == (
            f"{passport}/v{document.version}/en.pdf",
            f"{passport}/v{document.version}/ka.pdf",
        )
    )
    for path in second:
        stored = storage.get(path)
        assert stored is not None
        assert stored.startswith(b"%PDF")
        assert stored != b"stale-en"
        assert stored != b"stale-ka"


def test_sync_writes_pdfs_and_retries_only_missing_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pdf_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_role_key", "")
    store = MemorySyncStore()
    rows = [
        _row("ada@btu.edu.ge", HOLDER, ENGLISH_SKILL, "Stamp", "2025-06-01"),
        _row("ada@btu.edu.ge", HOLDER, "Python", "", ""),
        _row("ada@btu.edu.ge", HOLDER, OVERFLOW_SKILL, "Core", "2024-03-03"),
        _row("grace@btu.edu.ge", "Grace", "SQL", "", ""),
    ]
    created = run_sync(store, FakeSheet(rows))
    assert created.versions_created == 2
    ada = next(version for version in store.versions if version.email == "ada@btu.edu.ge")
    grace = next(version for version in store.versions if version.email == "grace@btu.edu.ge")
    assert ada.anchor_status == "pending"
    assert ada.tx_hash is None
    assert ada.pdf_en_path == f"{ada.passport_id}/v1/en.pdf"
    assert ada.pdf_ka_path == f"{ada.passport_id}/v1/ka.pdf"
    ka_path = tmp_path / ada.pdf_ka_path
    ka_text = "\n".join(page.extract_text() or "" for page in PdfReader(ka_path).pages)
    assert ENGLISH_SKILL in ka_text
    assert OVERFLOW_SKILL in ka_text
    assert "passport_api.chain" not in sys.modules
    en_file = tmp_path / f"{ada.passport_id}/v1/en.pdf"
    ada.pdf_en_path = None
    ada.pdf_ka_path = None
    grace.pdf_en_path = None
    grace.pdf_ka_path = None
    ka_path.unlink()
    en_file.unlink()
    again = run_sync(store, FakeSheet(rows[:3]))
    assert again.versions_created == 0
    assert ada.pdf_en_path == f"{ada.passport_id}/v1/en.pdf"
    assert ada.pdf_ka_path == f"{ada.passport_id}/v1/ka.pdf"
    assert (tmp_path / ada.pdf_ka_path).is_file()
    assert grace.pdf_en_path is None
    assert grace.pdf_ka_path is None


def _row(email: str, full_name: str, skill: str, badge: str, awarded_on: str) -> dict[str, str]:
    return {
        "email": email,
        "full_name": full_name,
        "skill": skill,
        "badge": badge,
        "awarded_on": awarded_on,
    }


def _assert_embedded_font_draws(pdf: bytes, sample: str) -> None:
    source = TTFontFile(str(FONT))
    ps_name = source.name.decode() if isinstance(source.name, bytes) else str(source.name)
    needed = {char for char in sample if _georgian(char)}
    seen: set[str] = set()
    reader = PdfReader(BytesIO(pdf))
    for page in reader.pages:
        resources = page.get("/Resources")
        if resources is None:
            continue
        fonts = resources.get_object().get("/Font")
        if fonts is None:
            continue
        for font in fonts.get_object().values():
            font_obj = font.get_object()
            if not isinstance(font_obj, DictionaryObject):
                continue
            base = str(font_obj.get("/BaseFont"))
            if not base.endswith(ps_name):
                continue
            widths = font_obj.get("/Widths")
            first = font_obj.get("/FirstChar")
            to_unicode = font_obj.get("/ToUnicode")
            if widths is None or first is None or to_unicode is None:
                continue
            mapping = _unicode_map(to_unicode.get_object().get_data())
            width_list = [int(item) for item in widths]
            origin = int(first)
            for char, code in mapping.items():
                if char not in needed or not 0 <= code - origin < len(width_list):
                    continue
                assert width_list[code - origin] == source.charWidths[ord(char)]
                seen.add(char)
    missing = needed - seen
    assert not missing


def _unicode_map(data: bytes) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for code, uni in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", data):
        if len(uni) != 4:
            continue
        mapping[chr(int(uni, 16))] = int(code, 16)
    return mapping


def _georgian(char: str) -> bool:
    code = ord(char)
    return 0x10A0 <= code <= 0x10FF or 0x1C90 <= code <= 0x1CBF or 0x2D00 <= code <= 0x2D2F
