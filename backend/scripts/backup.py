"""Export the database and the Google Sheet to a folder (the nightly backup job runs this).

Usage (in backend/): uv run python scripts/backup.py --out /path/to/folder

Reads SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, GOOGLE_SERVICE_ACCOUNT_JSON and SHEET_ID from
the environment (or backend/.env). Writes database/*.jsonl, sheet/*.csv and manifest.json.
It never prints a secret, a URL or a row: only table names, tab counts and row totals.

Exit codes: 0 everything saved, 1 bad arguments or missing settings, 2 something failed (the
manifest still lists what was saved and what went wrong).
"""

import argparse
import sys
from pathlib import Path

from passport_api.backup import (
    SHEET_READ_ONLY,
    BackupError,
    export_database,
    export_sheet,
    write_manifest,
)
from passport_api.settings import settings
from passport_api.sync import SheetUnavailableError, open_spreadsheet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--out", required=True, type=Path, help="folder to write into")
    args = parser.parse_args(argv)

    missing = [
        name
        for name, value in (
            ("SUPABASE_URL", settings.supabase_url),
            ("SUPABASE_SERVICE_ROLE_KEY", settings.supabase_service_role_key),
            ("GOOGLE_SERVICE_ACCOUNT_JSON", settings.google_service_account_json),
            ("SHEET_ID", settings.sheet_id),
        )
        if not value
    ]
    if missing:
        print(f"Missing settings: {', '.join(missing)}", file=sys.stderr)
        return 1

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    database = None
    sheet = None

    try:
        database = export_database(out, settings.supabase_url, settings.supabase_service_role_key)
        for table, count in database.items():
            print(f"database {table}: {count} rows")
    except BackupError as exc:
        errors.append(str(exc))
        print(f"ERROR {exc}", file=sys.stderr)

    try:
        spreadsheet = open_spreadsheet(timeout=60.0, scopes=SHEET_READ_ONLY)
        sheet = export_sheet(out, spreadsheet)
        for info in sheet.values():
            print(f"sheet tab: {info['rows']} rows")
    except SheetUnavailableError as exc:
        errors.append(f"sheet: {exc}")
        print(f"ERROR sheet: {exc}", file=sys.stderr)
    except BackupError as exc:
        errors.append(str(exc))
        print(f"ERROR {exc}", file=sys.stderr)

    write_manifest(out, database=database, sheet=sheet, errors=errors)
    if errors:
        print(f"Backup incomplete: {len(errors)} problem(s).", file=sys.stderr)
        return 2
    print("Backup complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
