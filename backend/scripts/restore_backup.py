"""Put an unpacked backup back (see docs/RESTORE.md). Dry run unless you pass --yes.

Usage (in backend/):
    uv run python scripts/restore_backup.py FOLDER                       # show what is inside
    uv run python scripts/restore_backup.py FOLDER --database --yes      # write the tables
    uv run python scripts/restore_backup.py FOLDER --sheet --yes         # write the Sheet

FOLDER is the decrypted and unpacked backup (it holds manifest.json). The database restore
upserts: rows with the same id are overwritten by the saved copy, other rows are left alone.
It needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY; the Sheet restore needs
GOOGLE_SERVICE_ACCOUNT_JSON and SHEET_ID, and the service account must be an Editor of the
Sheet. Run the migrations in supabase/migrations first when the database is brand new.
"""

import argparse
import sys
from pathlib import Path

from passport_api.backup import (
    BackupError,
    read_manifest,
    restore_database,
    restore_sheet,
)
from passport_api.settings import settings
from passport_api.sync import SheetUnavailableError, open_spreadsheet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--database", action="store_true", help="restore the tables")
    parser.add_argument("--sheet", action="store_true", help="restore the Google Sheet tabs")
    parser.add_argument("--yes", action="store_true", help="really write (default: dry run)")
    args = parser.parse_args(argv)

    try:
        manifest = read_manifest(args.folder)
    except BackupError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    print(f"Backup taken at {manifest['created_at']}")
    if manifest.get("errors"):
        print(f"WARNING this backup was incomplete: {manifest['errors']}")
    for table, count in (manifest.get("database") or {}).items():
        print(f"  database {table}: {count} rows")
    for info in (manifest.get("sheet") or {}).values():
        print(f"  sheet tab '{info['title']}': {info['rows']} rows")

    if not (args.database or args.sheet):
        print("Nothing selected. Add --database and/or --sheet (and --yes to write).")
        return 0
    if not args.yes:
        print("Dry run: nothing was written. Add --yes to restore for real.")
        return 0

    try:
        if args.database:
            if not settings.supabase_url or not settings.supabase_service_role_key:
                print("ERROR set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
                return 1
            done = restore_database(
                args.folder, settings.supabase_url, settings.supabase_service_role_key
            )
            for table, count in done.items():
                print(f"restored database {table}: {count} rows")
        if args.sheet:
            done_tabs = restore_sheet(args.folder, open_spreadsheet(timeout=120.0))
            for title, rows in done_tabs.items():
                print(f"restored sheet tab '{title}': {rows} rows")
    except (BackupError, SheetUnavailableError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    print("Restore finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
