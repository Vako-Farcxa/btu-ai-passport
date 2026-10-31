from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal, Protocol

from pypdf import PdfReader, PdfWriter
from reportlab import rl_config
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from storage3.types import FileOptions

from passport_api.db import get_supabase
from passport_api.schemas import Skill
from passport_api.settings import settings

# reportlab wraps every stream in ASCII85 on top of Flate by default, which makes images and
# font subsets about a quarter larger. Viewers read plain Flate, so turn the wrapping off.
rl_config.useA85 = 0

Language = Literal["en", "ka"]
_ASSETS = Path(__file__).resolve().parents[2] / "assets"
_FONTS = {False: "NotoSansGeorgian", True: "NotoSansGeorgian-Bold"}
_font_registered = False


@dataclass(frozen=True)
class PassportPdf:
    holder_name: str
    passport_id: str
    version: int
    issued_on: str
    verification_code: str
    skills: tuple[Skill, ...]
    # Explorer link once the version is anchored; None while pending.
    tx_url: str | None = None


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


# Layout of the official BTU template (assets/templates/passport-official.pdf,
# A4 landscape, 4 pages). Coordinates are measured from the top-left in points
# and flipped with _y() when drawing.
_PAGE_W = 841.89
_PAGE_H = 595.276
_CARD_COLS = ((78.0, 208.0), (218.0, 348.0), (357.0, 488.0), (497.0, 628.0), (637.0, 767.0))
_CARD_ROWS = ((118.0, 290.0), (300.0, 452.0))
_TABLE_COLS = (81.0, 204.0, 300.0, 446.0, 621.0, 764.0)
_TABLE_ROWS = (189.0, 243.0, 297.0, 351.0, 405.0, 459.0)
_INK = HexColor("#111111")
_MUTED = HexColor("#5f5f5f")
_ORANGE = HexColor("#ff5c1b")
_PANEL = Color(226 / 255, 223 / 255, 229 / 255)
_WHITE = Color(1, 1, 1)

_STAMP_LABELS: dict[str, dict[Language, str]] = {
    "BDG-AI-001": {"en": "AI SKILL", "ka": "AI უნარი"},
    "BDG-AI-002": {"en": "AI APPLIED SKILL", "ka": "AI გამოყენებითი უნარი"},
    "BDG-AI-003": {"en": "AI ADVANCED SKILL", "ka": "AI გაფართოებული უნარი"},
}

_KA_ABOUT = (
    "BTU AI უნარების ციფრული პასპორტი არის თქვენი პერსონალური და ვერიფიცირებადი "
    "ჩანაწერი უნივერსიტეტში სწავლისას განვითარებული AI კომპეტენციების შესახებ.",
    "AI უნარების შტამპების მოპოვება შესაძლებელია შესაბამისი აკადემიური კურსების, "
    "ვორქშოფების, მასტერკლასების, ჰაკათონების, ინტენსიური პროგრამების, მოწვეული "
    "სპიკერების სესიებისა და BTU-ს მიერ აღიარებული სხვა AI სასწავლო გამოცდილების მეშვეობით.",
    "პასპორტში მონაწილეობა ნებაყოფლობითია. შტამპების სავალდებულო რაოდენობა, კომბინაცია "
    "ან წინასწარ განსაზღვრული გზა არ არსებობს. სტუდენტები სასწავლო შესაძლებლობებს "
    "ირჩევენ საკუთარი ინტერესების, სწავლის, პროფესიული მიზნებისა და AI კომპეტენციის "
    "სასურველი სფეროების მიხედვით.",
    "ახალი კომპეტენციების განვითარებისა და აღიარების კვალდაკვალ პასპორტს ემატება ახალი "
    "შტამპები და თანდათან იქმნება ინდივიდუალური AI კომპეტენციების პროფილი.",
)
_KA_STAMPS = (
    # (heading box, title, subtitle, text box, text, represents)
    (
        (331.0, 126.0, 446.0, 157.0),
        "AI უნარი",
        "ფოკუსირებული სწავლება",
        (332.0, 162.0, 540.0, 248.0),
        "გაიცემა ფოკუსირებული სასწავლო გამოცდილებისთვის, როგორიცაა ვორქშოფი, "
        "მასტერკლასი, სემინარი, მოწვეული სპიკერის სესია ან მსგავსი მოკლე ფორმატის აქტივობა.",
        "ასახავს: განსაზღვრული AI კომპეტენციის განვითარებას.",
    ),
    (
        (563.0, 126.0, 670.0, 157.0),
        "AI გამოყენებითი უნარი",
        "გამოყენებითი სწავლება",
        (564.0, 162.0, 772.0, 250.0),
        "გაიცემა ხანგრძლივი პრაქტიკული სასწავლო გამოცდილებისთვის (როგორც წესი, ორი-სამი "
        "დღე), როგორიცაა ინტენსიური ვორქშოფი, ბუთქემფი, ჰაკათონი ან ჩელენჯი.",
        "ასახავს: განსაზღვრული AI კომპეტენციის პრაქტიკულ გამოყენებას.",
    ),
    (
        (331.0, 276.0, 512.0, 309.0),
        "AI გაფართოებული უნარი",
        "გაფართოებული აკადემიური სწავლება",
        (332.0, 313.0, 590.0, 406.0),
        "გაიცემა სემესტრული აკადემიური კურსის წარმატებით დასრულებისთვის, რომლის სწავლის "
        "შედეგების განსაზღვრულ და შეფასებულ კომპონენტს შესაბამისი AI კომპეტენცია წარმოადგენს.",
        "ასახავს: AI კომპეტენციის ხანგრძლივ და ფორმალურად შეფასებულ განვითარებას.",
    ),
)
_KA_GROWS = (
    ((697.0, 339.0, 728.0, 353.0), "სწავლა"),
    ((678.0, 378.0, 746.0, 392.0), "დემონსტრირება"),
    ((699.0, 410.0, 725.0, 424.0), "მოპოვება"),
    ((696.0, 449.0, 728.0, 462.0), "ვერიფიკაცია"),
    ((684.0, 487.0, 740.0, 510.0), "AI პროფილის შექმნა"),
)
_TABLE_HEAD: dict[Language, tuple[str, ...]] = {
    "en": ("STAMP TYPE", "SKILL", "DESCRIPTION", "EARNED THROUGH", "DATE EARNED"),
    "ka": ("შტამპის ტიპი", "უნარი", "აღწერა", "მიღების გზა", "მიღების თარიღი"),
}
_TEXT: dict[Language, dict[str, str]] = {
    "en": {
        "id": "PASSPORT ID:",
        "code": "Verification code",
        "chain": "Blockchain record (Polygon Amoy)",
        "pending": "pending, check status with the verification code on the BTU verify page",
        "page": "Page",
    },
    "ka": {
        "id": "პასპორტის ID:",
        "code": "ვერიფიკაციის კოდი",
        "chain": "ბლოკჩეინის ჩანაწერი (Polygon Amoy)",
        "pending": "მუშავდება, სტატუსი შეამოწმეთ ვერიფიკაციის კოდით BTU-ს ვერიფიკაციის გვერდზე",
        "page": "გვერდი",
    },
}


def render_pdf(lang: Language, document: PassportPdf) -> bytes:
    """One passport PDF. All text is drawn on a single reportlab document, so each font is
    embedded once (as a subset) and each stamp image once, and the template pages are slimmed
    and compressed (see _template_bytes). A typical passport is a few hundred KB."""
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(_PAGE_W, _PAGE_H), pageCompression=1)
    pages: list[int] = [0, 1]
    _cover_overlay(canvas, lang, document)
    _about_overlay(canvas, lang, document)
    cards = 10
    chunks = [document.skills[i : i + cards] for i in range(0, len(document.skills), cards)]
    for index, chunk in enumerate(chunks or [()]):
        _skillset_overlay(canvas, lang, document, chunk, index, len(chunks))
        pages.append(2)
    rows = len(_TABLE_ROWS) - 1
    chunks = [document.skills[i : i + rows] for i in range(0, len(document.skills), rows)]
    for index, chunk in enumerate(chunks or [()]):
        _details_overlay(canvas, lang, document, chunk, index, len(chunks))
        pages.append(3)
    canvas.save()
    overlay = PdfReader(BytesIO(buffer.getvalue()))
    writer = PdfWriter()
    for position, template_page in enumerate(pages):
        # A fresh reader per page so repeated template pages never share objects.
        page = PdfReader(BytesIO(_template_bytes())).pages[template_page]
        added = writer.add_page(page)
        added.merge_page(overlay.pages[position])
        added.compress_content_streams()
    # The four template pages carry the same three fonts. Keep one copy of anything identical.
    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _template_bytes() -> bytes:
    """The official template without what viewers never show.

    Adobe Illustrator saved its whole editable document (about 600 KB of private data), a
    thumbnail and XMP metadata inside the PDF. Every page of the output used to carry its own
    copy of all that. The visible pages (text, vectors, fonts, layers) are untouched."""
    global _template_cache
    if _template_cache is None:
        source = PdfReader(str(_ASSETS / "templates" / "passport-official.pdf"))
        writer = PdfWriter(clone_from=source)
        for page in writer.pages:
            for key in ("/PieceInfo", "/Thumb", "/LastModified"):
                if key in page:
                    del page[key]
        root = writer._root_object
        for key in ("/Metadata", "/PieceInfo"):
            if key in root:
                del root[key]
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
        slim = BytesIO()
        writer.write(slim)
        _template_cache = slim.getvalue()
    return _template_cache


_template_cache: bytes | None = None


def _y(top: float) -> float:
    return _PAGE_H - top


def _cover(canvas: Canvas, box: tuple[float, float, float, float], fill: Color = _WHITE) -> None:
    left, top, right, bottom = box
    canvas.saveState()
    canvas.setFillColor(fill)
    canvas.rect(left, _y(bottom), right - left, bottom - top, stroke=0, fill=1)
    canvas.restoreState()


def _cover_overlay(canvas: Canvas, lang: Language, document: PassportPdf) -> None:
    first, _, rest = document.holder_name.strip().partition(" ")
    name_x, surname_x, date_x = 196.0, 246.0, 648.0
    if lang == "ka":
        for box, _label in (
            ((105.0, 245.0, 190.0, 282.0), "სახელი:"),
            ((105.0, 286.0, 238.0, 322.0), "გვარი:"),
            ((590.0, 246.0, 644.0, 273.0), "თარიღი:"),
        ):
            _cover(canvas, box)
        canvas.setFillColor(_INK)
        name_x = 112 + _draw_runs(canvas, "სახელი:", 108, _y(273), 20, bold=True)
        surname_x = 112 + _draw_runs(canvas, "გვარი:", 108, _y(314), 20, bold=True)
        date_x = 598 + _draw_runs(canvas, "თარიღი:", 593, _y(267), 12, bold=True)
    canvas.setFillColor(_INK)
    _draw_fit(canvas, first, name_x, _y(273), 20, 560 - name_x, bold=True)
    _draw_fit(canvas, rest.strip(), surname_x, _y(314), 20, 560 - surname_x, bold=True)
    _draw_runs(canvas, document.issued_on, date_x, _y(267), 12)
    _passport_id(canvas, lang, document, right=True)
    _verification_lines(canvas, lang, document, 108, 500)
    canvas.showPage()


def _passport_id(canvas: Canvas, lang: Language, document: PassportPdf, right: bool) -> None:
    if right:
        if lang == "ka":
            _cover(canvas, (682.0, 477.0, 763.0, 496.0))
            canvas.setFillColor(_INK)
            _draw_runs(canvas, _TEXT[lang]["id"], 684, _y(491), 9)
        canvas.setFillColor(_INK)
        _draw_fit(canvas, document.passport_id, 684, _y(510), 11, 100, bold=True)
        return
    x = 152.0
    if lang == "ka":
        _cover(canvas, (70.0, 477.0, 150.0, 496.0))
        canvas.setFillColor(_INK)
        x = 76 + _draw_runs(canvas, _TEXT[lang]["id"], 72, _y(491), 9)
    canvas.setFillColor(_INK)
    _draw_runs(canvas, document.passport_id, x, _y(491), 11, bold=True)


def _verification_lines(
    canvas: Canvas, lang: Language, document: PassportPdf, x: float, top: float
) -> None:
    text = _TEXT[lang]
    canvas.setFillColor(_MUTED)
    _draw_runs(
        canvas,
        f"{text['code']}: {document.verification_code}   ·   v{document.version}",
        x,
        _y(top),
        7.5,
    )
    line_top = top + 11
    if document.tx_url is None:
        _draw_block(canvas, f"{text['chain']}: {text['pending']}", x, line_top - 7.5, 250, 7.5, 9.5)
        return
    url = document.tx_url
    shown = url.split("://", 1)[-1]
    if len(shown) > 44:
        shown = f"{shown[:36]}…{shown[-6:]}"
    label = f"{text['chain']}: {shown}"
    width = _text_width(label, 7.5)
    _draw_runs(canvas, label, x, _y(line_top), 7.5)
    # Clickable, while the printed text stays short enough to clear the cover stamps.
    canvas.linkURL(url, (x, _y(line_top) - 2, x + width, _y(line_top) + 8), relative=0)


def _about_overlay(canvas: Canvas, lang: Language, document: PassportPdf) -> None:
    if lang == "ka":
        _about_georgian(canvas)
    _passport_id(canvas, lang, document, right=False)
    canvas.showPage()


def _about_georgian(canvas: Canvas) -> None:
    _cover(canvas, (72.0, 77.0, 300.0, 172.0))
    canvas.setFillColor(_INK)
    _draw_block(canvas, "AI უნარების ციფრული პასპორტის შესახებ", 74, 100, 220, 17, 22, bold=True)
    _cover(canvas, (72.0, 178.0, 300.0, 414.0))
    top = 188.0
    for paragraph in _KA_ABOUT:
        top = _draw_block(canvas, paragraph, 74, top, 222, 7.2, 9.6) + 6
    _cover(canvas, (330.0, 77.0, 780.0, 116.0))
    canvas.setFillColor(_ORANGE)
    _draw_runs(canvas, "AI უნარების შტამპების განმარტება", 332, _y(106), 21, bold=True)
    for heading, title, subtitle, box, body, represents in _KA_STAMPS:
        _cover(canvas, heading)
        canvas.setFillColor(_INK)
        _draw_fit(
            canvas,
            title,
            heading[0] + 2,
            _y(heading[1] + 14),
            10.5,
            heading[2] - heading[0] - 4,
            bold=True,
        )
        _draw_fit(
            canvas, subtitle, heading[0] + 2, _y(heading[1] + 27), 8, heading[2] - heading[0] - 4
        )
        _cover(canvas, box)
        width = box[2] - box[0] - 4
        end = _draw_block(canvas, body, box[0] + 2, box[1] + 9, width, 7.4, 10)
        _draw_block(canvas, represents, box[0] + 2, end + 6, width, 7.4, 10, bold=True)
    _cover(canvas, (650.0, 276.0, 780.0, 310.0))
    canvas.setFillColor(_INK)
    _draw_centered(canvas, "როგორ იზრდება", 713, _y(290), 10.5, bold=True)
    _draw_centered(canvas, "პასპორტი", 713, _y(304), 10.5, bold=True)
    for box, label in _KA_GROWS:
        _cover(canvas, box)
        canvas.setFillColor(_INK)
        _draw_centered(canvas, label, (box[0] + box[2]) / 2, _y(box[3] - 3), 7.5)
    _cover(canvas, (339.0, 429.0, 621.0, 504.0), _PANEL)
    canvas.setFillColor(_INK)
    _draw_runs(canvas, "მნიშვნელოვანი", 342, _y(442), 9, bold=True)
    end = _draw_block(
        canvas,
        "შტამპის სამი ტიპი ასახავს სწავლის სხვადასხვა ფორმატსა და ჩართულობის სიღრმეს. "
        "ისინი არ ქმნიან სავალდებულო თანმიმდევრობას.",
        342,
        455,
        272,
        6.8,
        9,
    )
    _draw_block(
        canvas,
        "სტუდენტს არ სჭირდება AI უნარის მოპოვება AI გამოყენებითი ან AI გაფართოებული "
        "უნარის მოპოვებამდე.",
        342,
        end + 4,
        272,
        6.8,
        9,
    )


def _page_titles(canvas: Canvas, title: str, subtitle: str, width: float) -> None:
    _cover(canvas, (72.0, 76.0, 75.0 + width, 126.0))
    canvas.setFillColor(_INK)
    _draw_runs(canvas, title, 74, _y(103), 19, bold=True)
    _draw_runs(canvas, subtitle, 76, _y(120), 8.5, bold=True)


def _page_marker(canvas: Canvas, lang: Language, index: int, total: int, top: float) -> None:
    if total < 2:
        return
    canvas.setFillColor(_MUTED)
    _draw_runs(canvas, f"{_TEXT[lang]['page']} {index + 1}/{total}", 400, _y(top), 8)


def _skillset_overlay(
    canvas: Canvas,
    lang: Language,
    document: PassportPdf,
    skills: tuple[Skill, ...],
    index: int,
    total: int,
) -> None:
    if lang == "ka":
        _page_titles(
            canvas,
            "ვერიფიცირებული AI უნარები",
            "BTU-ს მიერ ვერიფიცირებული AI უნარების შტამპები",
            330,
        )
    for slot, skill in enumerate(skills):
        left, right = _CARD_COLS[slot % len(_CARD_COLS)]
        top, bottom = _CARD_ROWS[slot // len(_CARD_COLS)]
        _cover(canvas, (left + 6, top + 6, right - 6, bottom - 6))
        center = (left + right) / 2
        canvas.setFillColor(_MUTED)
        _draw_centered(canvas, skill.awarded_on or "", center, _y(top + 20), 7.5)
        _draw_stamp(canvas, skill.badge, (left + 10, top + 28, right - 10, top + 92))
        canvas.setFillColor(_INK)
        end = _draw_block(
            canvas,
            skill.skill.upper(),
            left + 8,
            top + 110,
            right - left - 16,
            8,
            10,
            bold=True,
            center=True,
            max_lines=3,
        )
        canvas.setFillColor(_MUTED)
        _draw_block(
            canvas,
            _stamp_label(lang, skill.badge),
            left + 8,
            end + 2,
            right - left - 16,
            7,
            9,
            center=True,
            max_lines=2,
        )
    _page_marker(canvas, lang, index, total, 470)
    _passport_id(canvas, lang, document, right=True)
    canvas.showPage()


def _details_overlay(
    canvas: Canvas,
    lang: Language,
    document: PassportPdf,
    skills: tuple[Skill, ...],
    index: int,
    total: int,
) -> None:
    if lang == "ka":
        _page_titles(
            canvas,
            "AI უნარების დანართი",
            "ვერიფიცირებული AI უნარებისა და სასწავლო გამოცდილების დეტალური ჩანაწერი",
            420,
        )
        _cover(canvas, (84.0, 157.0, 761.0, 184.0))
        canvas.setFillColor(_INK)
        for column, label in enumerate(_TABLE_HEAD[lang]):
            middle = (_TABLE_COLS[column] + _TABLE_COLS[column + 1]) / 2
            _draw_centered(canvas, label, middle, _y(174), 8.5, bold=True)
    cols = _TABLE_COLS
    for row, skill in enumerate(skills):
        top, bottom = _TABLE_ROWS[row], _TABLE_ROWS[row + 1]
        _cover(canvas, (cols[0] + 2, top + 2, cols[1] - 2, bottom - 2))
        _draw_stamp(canvas, skill.badge, (cols[0] + 8, top + 7, cols[1] - 8, bottom - 7))
        canvas.setFillColor(_INK)
        _draw_middle(canvas, skill.skill.upper(), cols[1], cols[2], top, bottom, 7.5, 9.5, True)
        canvas.setFillColor(_MUTED)
        _draw_middle(canvas, skill.description.strip(), cols[2], cols[3], top, bottom, 6, 7.4)
        # The sheet has no "earned through" source column, so it stays blank.
        canvas.setFillColor(_INK)
        _draw_middle(canvas, skill.awarded_on or "", cols[4], cols[5], top, bottom, 8, 10)
    _page_marker(canvas, lang, index, total, 470)
    _passport_id(canvas, lang, document, right=False)
    _verification_lines(canvas, lang, document, 72, 508)
    canvas.showPage()


def _draw_middle(
    canvas: Canvas,
    text: str,
    left: float,
    right: float,
    top: float,
    bottom: float,
    size: float,
    leading: float,
    bold: bool = False,
) -> None:
    if not text:
        return
    width = right - left - 10
    max_lines = max(1, int((bottom - top - 6) // leading))
    lines = _wrap(text, width, size, bold, max_lines)
    start = (top + bottom) / 2 - leading * len(lines) / 2 + size
    for offset, line in enumerate(lines):
        _draw_centered(canvas, line, (left + right) / 2, _y(start + offset * leading), size, bold)


def _stamp_label(lang: Language, badge: str) -> str:
    labels = _STAMP_LABELS.get(badge.strip().upper())
    return badge if labels is None else labels[lang]


def _draw_stamp(canvas: Canvas, badge: str, box: tuple[float, float, float, float]) -> None:
    path = _ASSETS / "stamps" / f"{badge.strip().upper()}.png"
    if not badge.strip() or not path.is_file():
        return
    image = ImageReader(str(path))
    width, height = image.getSize()
    left, top, right, bottom = box
    scale = min((right - left) / width, (bottom - top) / height)
    w, h = width * scale, height * scale
    x = left + (right - left - w) / 2
    y = _y(top + (bottom - top + h) / 2)
    canvas.drawImage(image, x, y, w, h, mask="auto")


def _draw_block(
    canvas: Canvas,
    text: str,
    x: float,
    top: float,
    width: float,
    size: float,
    leading: float,
    bold: bool = False,
    center: bool = False,
    max_lines: int | None = None,
) -> float:
    """Draw wrapped text from a top-left anchor; return the top of the next line."""
    lines = _wrap(text, width, size, bold, max_lines)
    baseline = top + size
    for line in lines:
        if center:
            _draw_centered(canvas, line, x + width / 2, _y(baseline), size, bold)
        else:
            _draw_runs(canvas, line, x, _y(baseline), size, bold)
        baseline += leading
    return baseline - size


def _wrap(text: str, width: float, size: float, bold: bool, max_lines: int | None) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and _text_width(candidate, size, bold) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and _text_width(last + "…", size, bold) > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def _draw_fit(
    canvas: Canvas, text: str, x: float, y: float, size: float, width: float, bold: bool = False
) -> None:
    while size > 6 and _text_width(text, size, bold) > width:
        size -= 0.5
    _draw_runs(canvas, text, x, y, size, bold)


def _draw_centered(
    canvas: Canvas, text: str, center: float, y: float, size: float, bold: bool = False
) -> None:
    _draw_runs(canvas, text, center - _text_width(text, size, bold) / 2, y, size, bold)


def _font_for(georgian: bool, bold: bool) -> str:
    if georgian:
        return _georgian_font(bold)
    return "Helvetica-Bold" if bold else "Helvetica"


def _text_width(text: str, size: float, bold: bool = False) -> float:
    return sum(
        float(pdfmetrics.stringWidth(run, _font_for(georgian, bold), size))
        for georgian, run in _runs(text)
    )


def _draw_runs(
    canvas: Canvas, text: str, x: float, y: float, size: float, bold: bool = False
) -> float:
    cursor = x
    for georgian, run in _runs(text):
        font_name = _font_for(georgian, bold)
        canvas.setFont(font_name, size)
        canvas.drawString(cursor, y, run)
        cursor += canvas.stringWidth(run, font_name, size)
    return float(cursor - x)


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


def _georgian_font(bold: bool = False) -> str:
    global _font_registered
    if not _font_registered:
        for weight, file_name in (
            (False, "NotoSansGeorgian-Regular.ttf"),
            (True, "NotoSansGeorgian-Bold.ttf"),
        ):
            path = _ASSETS / "fonts" / file_name
            if not path.is_file():
                raise FileNotFoundError("georgian_font_missing")
            pdfmetrics.registerFont(TTFont(_FONTS[weight], str(path)))
        _font_registered = True
    return _FONTS[bold]


def _default_storage_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "var" / "passports"
