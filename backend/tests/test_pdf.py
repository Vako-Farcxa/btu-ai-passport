import re
from dataclasses import replace
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
BOLD_FONT = ASSETS / "fonts" / "NotoSansGeorgian-Bold.ttf"

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


def _text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)


def test_official_four_page_layout_in_both_languages() -> None:
    document = _document()
    for lang in ("en", "ka"):
        pdf = render_pdf(lang, document)
        reader = PdfReader(BytesIO(pdf))
        assert len(reader.pages) == 4
        assert reader.pages[0].mediabox.width > reader.pages[0].mediabox.height
        text = _text(pdf)
        for part in HOLDER.split():
            assert part in text
        assert ENGLISH_SKILL.upper() in text
        assert OVERFLOW_SKILL.upper() in text
        assert document.passport_id in text
        assert document.verification_code in text
    assert "სახელი" in _text(render_pdf("ka", document))
    assert "AI APPLIED SKILL" in _text(render_pdf("en", document))


def test_many_skills_paginate_grid_and_table() -> None:
    skills = tuple(
        Skill(skill=f"Skill {index}", badge="BDG-AI-002", awarded_on="2026-01-01")
        for index in range(12)
    )
    document = replace(_document(), skills=skills)
    reader = PdfReader(BytesIO(render_pdf("en", document)))
    # cover + about + 2 grid pages (10 per page) + 3 table pages (5 per page)
    assert len(reader.pages) == 7
    assert "Skill 11" in (reader.pages[3].extract_text() or "").title()


def test_stamp_images_are_drawn_for_known_badges() -> None:
    document = replace(
        _document(),
        skills=(Skill(skill="AI Literacy", badge="BDG-AI-001", awarded_on="2026-01-01"),),
    )
    plain = replace(document, skills=(Skill(skill="AI Literacy", badge="X", awarded_on=None),))
    with_stamp = PdfReader(BytesIO(render_pdf("en", document))).pages[2]
    without = PdfReader(BytesIO(render_pdf("en", plain))).pages[2]
    assert len(with_stamp.images) > len(without.images)


def test_blockchain_link_is_printed_when_known() -> None:
    url = "https://amoy.polygonscan.com/tx/0xabc"
    text = _text(render_pdf("en", replace(_document(), tx_url=url)))
    assert "amoy.polygonscan.com/tx/0xabc" in text
    assert "pending" in _text(render_pdf("en", _document()))


def test_georgian_text_is_drawn_with_the_asset_font() -> None:
    document = _document()
    pdf = render_pdf("ka", document)
    text = _text(pdf)
    for part in HOLDER.split():
        assert part in text
    assert OVERFLOW_SKILL.upper() in text
    assert ENGLISH_SKILL.upper() in text
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
    assert ENGLISH_SKILL.upper() in ka_text
    assert OVERFLOW_SKILL.upper() in ka_text
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
    ka_written = ada.pdf_ka_path
    assert ka_written is not None
    assert (tmp_path / ka_written).is_file()
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
    sources = {}
    for path in (FONT, BOLD_FONT):
        font_file = TTFontFile(str(path))
        name = font_file.name
        sources[name.decode() if isinstance(name, bytes) else str(name)] = font_file
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
            source = next((f for n, f in sources.items() if base.endswith(n)), None)
            if source is None:
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
