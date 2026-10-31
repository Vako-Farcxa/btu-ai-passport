"""Export the database and the Google Sheet to plain files, and put them back.

The nightly GitHub Actions job (.github/workflows/backup.yml) runs scripts/backup.py, which
calls `export_database` and `export_sheet`, then encrypts the result. docs/RESTORE.md
explains the way back, which scripts/restore_backup.py does with `restore_database` and
`restore_sheet`.

- Database: every table in TABLES is read through Supabase's REST API with the service role
  key, page by page, into one JSON Lines file per table (`database/<table>.jsonl`). JSON keeps
  ids, timestamps, arrays and jsonb exactly. The rows written must be at least the total the
  API reports at the start, otherwise the export fails instead of quietly saving a part.
- Sheet: each tab becomes `sheet/<nn>.csv` (the values as displayed), and the manifest maps
  the numbers to tab titles. Formatting, formulas and validation rules are not saved.
- Messages: an error here names the table or tab and an HTTP status, never a URL, a key, a
  response body or a row, so a log of a run holds no secrets and no personal data.

Not backed up: Supabase Auth users (they are created again when someone signs in), the
Storage bucket with the PDFs (the admin panel regenerates them), and the anchors on the
blockchain (they are public and permanent).
"""

import csv
import json
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

import httpx

# Parents before children, so a restore never meets a foreign key to a row that is not there:
# skill_entries.skill_id -> skills, passport_versions -> students, skill_entries -> versions,
# flags.passport_id -> students.
TABLES: tuple[str, ...] = (
    "skills",
    "students",
    "passport_versions",
    "skill_entries",
    "source_records",
    "sync_runs",
    "admin_users",
    "flags",
)
# Tables that are deliberately not saved. The anchor lock only holds "a run is in progress",
# and migration 0010 creates its one row again. tests/test_backup.py checks that TABLES and
# this tuple together cover every table the migrations create.
SKIPPED_TABLES: tuple[str, ...] = ("anchor_reconcile_lock",)

PAGE_SIZE = 1000
RESTORE_BATCH = 500
REQUEST_TIMEOUT = 60.0
SHEET_READ_ONLY = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
FORMAT_VERSION = 1


class BackupError(Exception):
    """A failure whose message is safe to print: it never carries a URL, key or row."""


class Worksheet(Protocol):
    title: str

    def get_all_values(self) -> list[list[str]]: ...


class Spreadsheet(Protocol):
    def worksheets(self) -> Sequence[Worksheet]: ...


def _headers(key: str) -> dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _base(url: str) -> str:
    return f"{url.rstrip('/')}/rest/v1"


def export_table(client: httpx.Client, url: str, key: str, table: str, path: Path) -> int:
    """Write every row of `table` to `path` as JSON Lines. Returns the row count.

    Pages are read by id (`id > last id seen`), not by offset, so a row added while the export
    runs cannot shift the pages and make it skip or repeat a row."""
    written = 0
    total: int | None = None
    last_id: str | None = None
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        while True:
            params = {"select": "*", "order": "id.asc", "limit": str(PAGE_SIZE)}
            headers = _headers(key)
            if last_id is None:
                headers["Prefer"] = "count=exact"
            else:
                params["id"] = f"gt.{last_id}"
            try:
                response = client.get(f"{_base(url)}/{table}", params=params, headers=headers)
            except httpx.TimeoutException as exc:
                raise BackupError(f"table {table}: request timed out") from exc
            except httpx.HTTPError as exc:
                raise BackupError(f"table {table}: request failed ({type(exc).__name__})") from exc
            if response.status_code not in (200, 206):
                raise BackupError(f"table {table}: HTTP {response.status_code}")
            if last_id is None:
                total = _total(response.headers.get("content-range"), None)
            rows = response.json()
            if not isinstance(rows, list):
                raise BackupError(f"table {table}: unexpected response")
            # Stop on an empty page. The server may cap a page below PAGE_SIZE, so a short
            # page is not the end.
            if not rows:
                break
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            written += len(rows)
            last_id = str(rows[-1]["id"])
    # More rows than counted at the start is fine (something was added meanwhile). Fewer means
    # the API handed back less than it said it had.
    if total is None or written < total:
        raise BackupError(f"table {table}: wrote {written} rows but the database has {total}")
    return written


def _total(content_range: str | None, previous: int | None) -> int | None:
    """The row total from a header such as `0-999/2345` (or `*/0`)."""
    if content_range is None or "/" not in content_range:
        return previous
    tail = content_range.rsplit("/", 1)[1]
    return int(tail) if tail.isdigit() else previous


def export_database(
    out_dir: Path, url: str, key: str, *, client: httpx.Client | None = None
) -> dict[str, int]:
    own = client is None
    http = client or httpx.Client(timeout=REQUEST_TIMEOUT)
    try:
        return {
            table: export_table(http, url, key, table, out_dir / "database" / f"{table}.jsonl")
            for table in TABLES
        }
    finally:
        if own:
            http.close()


def export_sheet(out_dir: Path, spreadsheet: Spreadsheet) -> dict[str, dict[str, Any]]:
    """Each tab as `sheet/<nn>.csv`. Returns {file name: {"title": ..., "rows": n}}."""
    folder = out_dir / "sheet"
    folder.mkdir(parents=True, exist_ok=True)
    tabs: dict[str, dict[str, Any]] = {}
    for number, worksheet in enumerate(spreadsheet.worksheets(), start=1):
        name = f"{number:02d}.csv"
        try:
            values = worksheet.get_all_values()
        except Exception as exc:
            raise BackupError(f"sheet tab {number}: read failed ({type(exc).__name__})") from exc
        with (folder / name).open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerows(values)
        tabs[name] = {"title": worksheet.title, "rows": len(values)}
    if not tabs:
        raise BackupError("sheet: the spreadsheet has no tabs")
    return tabs


def write_manifest(
    out_dir: Path,
    *,
    database: dict[str, int] | None,
    sheet: dict[str, dict[str, Any]] | None,
    errors: Sequence[str],
    now: datetime | None = None,
) -> Path:
    manifest = {
        "format": FORMAT_VERSION,
        "created_at": (now or datetime.now(UTC)).isoformat(),
        "database": database,
        "sheet": sheet,
        "errors": list(errors),
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def read_manifest(folder: Path) -> dict[str, Any]:
    path = folder / "manifest.json"
    if not path.is_file():
        raise BackupError(f"{folder}: no manifest.json, this is not an unpacked backup")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != FORMAT_VERSION:
        raise BackupError("manifest.json: unknown backup format")
    return cast(dict[str, Any], data)


def _batches(path: Path, size: int) -> Iterable[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                batch.append(json.loads(line))
            if len(batch) >= size:
                yield batch
                batch = []
    if batch:
        yield batch


def restore_database(
    folder: Path,
    url: str,
    key: str,
    *,
    tables: Sequence[str] = TABLES,
    client: httpx.Client | None = None,
) -> dict[str, int]:
    """Upsert every saved row, tables in dependency order. Existing rows with the same id are
    overwritten by the saved copy; rows that are not in the backup are left alone."""
    own = client is None
    http = client or httpx.Client(timeout=REQUEST_TIMEOUT)
    restored: dict[str, int] = {}
    try:
        for table in TABLES:
            if table not in tables:
                continue
            path = folder / "database" / f"{table}.jsonl"
            if not path.is_file():
                raise BackupError(f"table {table}: file missing from the backup")
            count = 0
            for batch in _batches(path, RESTORE_BATCH):
                try:
                    response = http.post(
                        f"{_base(url)}/{table}",
                        headers={
                            **_headers(key),
                            "Content-Type": "application/json",
                            "Prefer": "resolution=merge-duplicates,return=minimal",
                        },
                        content=json.dumps(batch, ensure_ascii=False).encode("utf-8"),
                    )
                except httpx.HTTPError as exc:
                    raise BackupError(
                        f"table {table}: request failed ({type(exc).__name__})"
                    ) from exc
                if response.status_code not in (200, 201, 204):
                    raise BackupError(f"table {table}: HTTP {response.status_code}")
                count += len(batch)
            restored[table] = count
    finally:
        if own:
            http.close()
    return restored


def restore_sheet(folder: Path, spreadsheet: Any) -> dict[str, int]:
    """Write every saved tab back. A tab that exists is cleared first; a missing one is
    created. Values are entered as if typed, so dates and numbers stay dates and numbers."""
    manifest = read_manifest(folder)
    tabs: dict[str, dict[str, Any]] = manifest.get("sheet") or {}
    if not tabs:
        raise BackupError("the backup has no sheet data")
    existing = {worksheet.title: worksheet for worksheet in spreadsheet.worksheets()}
    restored: dict[str, int] = {}
    for name, info in tabs.items():
        title = str(info["title"])
        with (folder / "sheet" / name).open(encoding="utf-8", newline="") as handle:
            values = list(csv.reader(handle))
        width = max((len(row) for row in values), default=1)
        rows = max(len(values), 1)
        worksheet = existing.get(title)
        if worksheet is None:
            worksheet = spreadsheet.add_worksheet(title=title, rows=rows, cols=width)
        else:
            worksheet.clear()
            if worksheet.row_count < rows or worksheet.col_count < width:
                worksheet.resize(
                    rows=max(rows, worksheet.row_count), cols=max(width, worksheet.col_count)
                )
        if values:
            worksheet.update(values, "A1", value_input_option="USER_ENTERED")
        restored[title] = len(values)
    return restored
