import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal, Protocol

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, NumberObject, TextStringObject
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from storage3.types import FileOptions

from passport_api.db import get_supabase
from passport_api.schemas import Skill
from passport_api.settings import settings

Language = Literal["en", "ka"]
_ASSETS = Path(__file__).resolve().parents[2] / "assets"
_FONT_NAME = "NotoSansGeorgian"
_font_registered = False


@dataclass(frozen=True)
class PassportPdf:
    holder_name: str
    passport_id: str
    version: int
    issued_on: str
    verification_code: str
    skills: tuple[Skill, ...]


class ObjectStorage(Protocol):
    def put(self, path: str, data: bytes) -> None: ...

    def get(self, path: str) -> bytes | None: ...


class LocalPdfStorage:
    def __init__(self, root: Path) -> None:
        self._root = root

    def put(self, path: str, data: bytes) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def get(self, path: str) -> bytes | None:
        target = self._resolve(path)
        if not target.is_file():
            return None
        return target.read_bytes()

    def _resolve(self, path: str) -> Path:
        if path.startswith(("/", "\\")) or "\\" in path:
            raise ValueError("invalid_path")
        if any(part == ".." for part in Path(path).parts):
            raise ValueError("invalid_path")
        root = self._root.resolve()
        target = (root / path).resolve()
        if not target.is_relative_to(root):
            raise ValueError("invalid_path")
        return target


class SupabasePdfStorage:
    def put(self, path: str, data: bytes) -> None:
        options: FileOptions = {"content-type": "application/pdf", "upsert": "true"}
        get_supabase().storage.from_("passports").upload(path, data, file_options=options)

    def get(self, path: str) -> bytes | None:
        try:
            return get_supabase().storage.from_("passports").download(path)
        except Exception:
            return None


def get_storage() -> ObjectStorage:
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabasePdfStorage()
    root = Path(settings.pdf_storage_dir) if settings.pdf_storage_dir else _default_storage_dir()
    return LocalPdfStorage(root)


def storage_paths(passport_id: str, version: int) -> tuple[str, str]:
    base = f"{passport_id}/v{version}"
    return f"{base}/en.pdf", f"{base}/ka.pdf"


def publish_pdfs(document: PassportPdf, storage: ObjectStorage) -> tuple[str, str]:
    en_path, ka_path = storage_paths(document.passport_id, document.version)
    storage.put(en_path, render_pdf("en", document))
    storage.put(ka_path, render_pdf("ka", document))
    return en_path, ka_path


def render_pdf(lang: Language, document: PassportPdf) -> bytes:
    template_name = "passport-en.pdf" if lang == "en" else "passport-ka.pdf"
    field_map = _field_maps()[template_name]
    reader = PdfReader(str(_ASSETS / "templates" / template_name))
    writer = PdfWriter()
    writer.append(reader)
    page = writer.pages[0]
    acro_values = {
        field_map[name]: value for name, value in _canonical_values(document, field_map).items()
    }
    rects = _widget_rects(page)
    for widget in _widgets(page):
        name = str(widget.get("/T"))
        if name not in acro_values:
            continue
        widget[NameObject("/V")] = TextStringObject(acro_values[name])
        widget[NameObject("/F")] = NumberObject(2)
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    overlay = _overlay(rects, acro_values, (width, height))
    page.merge_page(PdfReader(BytesIO(overlay)).pages[0])
    slots = _slot_count(field_map)
    extra = _overflow_pdf(lang, document.skills[slots:], (width, height))
    if extra is not None:
        writer.append(PdfReader(BytesIO(extra)))
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _default_storage_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "var" / "passports"


def _field_maps() -> dict[str, dict[str, str]]:
    payload = json.loads((_ASSETS / "templates" / "fields.json").read_text())
    if not isinstance(payload, dict):
        raise ValueError("fields_json")
    maps: dict[str, dict[str, str]] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise ValueError("fields_json")
        maps[key] = {str(name): str(target) for name, target in value.items()}
    return maps


def _slot_count(field_map: dict[str, str]) -> int:
    indexes = [
        int(key.split("_")[1])
        for key in field_map
        if key.startswith("skill_") and key.endswith("_name")
    ]
    if not indexes:
        raise ValueError("skill_slots_missing")
    return max(indexes)


def _canonical_values(document: PassportPdf, field_map: dict[str, str]) -> dict[str, str]:
    slots = _slot_count(field_map)
    base = {
        "holder_name": document.holder_name,
        "passport_id": document.passport_id,
        "version": str(document.version),
        "issued_on": document.issued_on,
        "verification_code": document.verification_code,
    }
    for index in range(1, slots + 1):
        skill = document.skills[index - 1] if index <= len(document.skills) else None
        base[f"skill_{index}_name"] = "" if skill is None else skill.skill
        base[f"skill_{index}_badge"] = "" if skill is None else skill.badge
        awarded = "" if skill is None or skill.awarded_on is None else skill.awarded_on
        base[f"skill_{index}_date"] = awarded
    return {name: base[name] for name in field_map}


def _widgets(page: object) -> list[DictionaryObject]:
    getter = getattr(page, "get", None)
    if getter is None:
        return []
    raw = getter("/Annots")
    if raw is None:
        return []
    annots = raw.get_object()
    if not isinstance(annots, list):
        return []
    widgets: list[DictionaryObject] = []
    for annot in annots:
        obj = annot.get_object() if hasattr(annot, "get_object") else annot
        if isinstance(obj, DictionaryObject):
            widgets.append(obj)
    return widgets


def _widget_rects(page: object) -> dict[str, tuple[float, float, float, float]]:
    rects: dict[str, tuple[float, float, float, float]] = {}
    for widget in _widgets(page):
        name = widget.get("/T")
        rect = widget.get("/Rect")
        if name is None or rect is None:
            continue
        box = tuple(float(item) for item in rect)
        if len(box) != 4:
            continue
        rects[str(name)] = (box[0], box[1], box[2], box[3])
    return rects


def _overlay(
    rects: dict[str, tuple[float, float, float, float]],
    values: dict[str, str],
    page_size: tuple[float, float],
) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=page_size)
    for name, value in values.items():
        if not value or name not in rects:
            continue
        left, bottom, _right, _top = rects[name]
        _draw_runs(canvas, value, left + 2, bottom + 4, 9)
    canvas.save()
    return buffer.getvalue()


def _overflow_pdf(
    lang: Language,
    skills: tuple[Skill, ...],
    page_size: tuple[float, float],
) -> bytes | None:
    if not skills:
        return None
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=page_size)
    _height = page_size[1]
    title = "Additional skills" if lang == "en" else "დამატებითი უნარები"
    chunk = 24
    for start in range(0, len(skills), chunk):
        _draw_runs(canvas, title, 40, _height - 48, 14)
        y = _height - 80
        for skill in skills[start : start + chunk]:
            date = "" if skill.awarded_on is None else skill.awarded_on
            line = "  ".join(part for part in (skill.skill, skill.badge, date) if part)
            _draw_runs(canvas, line, 40, y, 11)
            y -= 22
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _draw_runs(canvas: Canvas, text: str, x: float, y: float, size: float) -> None:
    cursor = x
    for georgian, run in _runs(text):
        font_name = _font_name() if georgian else "Helvetica"
        canvas.setFont(font_name, size)
        canvas.drawString(cursor, y, run)
        cursor += canvas.stringWidth(run, font_name, size)


def _runs(text: str) -> list[tuple[bool, str]]:
    runs: list[tuple[bool, str]] = []
    current: bool | None = None
    buffer = ""
    for char in text:
        if char.isspace() and current is not None:
            buffer += char
            continue
        georgian = _is_georgian(char)
        if current is None:
            current = georgian
            buffer = char
            continue
        if georgian != current:
            runs.append((current, buffer))
            buffer = char
            current = georgian
            continue
        buffer += char
    if buffer and current is not None:
        runs.append((current, buffer))
    return runs


def _is_georgian(char: str) -> bool:
    code = ord(char)
    return 0x10A0 <= code <= 0x10FF or 0x1C90 <= code <= 0x1CBF or 0x2D00 <= code <= 0x2D2F


def _font_name() -> str:
    global _font_registered
    if not _font_registered:
        fonts = sorted((_ASSETS / "fonts").glob("*.ttf"))
        if not fonts:
            raise FileNotFoundError("georgian_font_missing")
        pdfmetrics.registerFont(TTFont(_FONT_NAME, str(fonts[0])))
        _font_registered = True
    return _FONT_NAME
