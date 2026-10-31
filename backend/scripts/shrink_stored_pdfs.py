"""Re-render the stored passport PDFs with the slim renderer, in place (same paths).

PDFs written before the performance work are about 5.8 MB each (the official template was
copied whole onto every page with its Illustrator editing data). The same passport renders to
well under 500 KB now, pixel for pixel. This replaces the stored files so the free Supabase
storage (1 GB) holds thousands of versions instead of about 170.

Usage (run in backend/, which reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from .env):
    uv run python scripts/shrink_stored_pdfs.py            # dry run: sizes only, changes nothing
    uv run python scripts/shrink_stored_pdfs.py --apply    # upload the slim files
    uv run python scripts/shrink_stored_pdfs.py --apply --with-tx-links

The files are rendered the way the sync renders them (no transaction link). Add
--with-tx-links to keep a link to the confirmed anchor transaction on the details page, like
scripts/backfill_descriptions.py --pdfs does. A version is only replaced when the new file is
smaller than the stored one, and the content (names, skills, codes) comes from the database,
so the verification code and hashes on the page are unchanged.
"""

import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from passport_api.chain import tx_url
from passport_api.db import get_supabase
from passport_api.pdf import Language, PassportPdf, get_storage, render_pdf
from passport_api.store import StoredVersion
from passport_api.supabase_store import SupabaseStore
from passport_api.sync import _select_all

WORKERS = 4


def _emails() -> list[str]:
    rows = _select_all(lambda: get_supabase().table("students").select("email").order("email"))
    return [str(row["email"]) for row in rows]


def _document(version: StoredVersion, with_links: bool) -> PassportPdf:
    return PassportPdf(
        holder_name=version.holder_name,
        passport_id=version.passport_id,
        version=version.version,
        issued_on=version.issued_at[:10],
        verification_code=version.verification_code,
        skills=version.skills,
        tx_url=(
            tx_url(version.tx_hash)
            if with_links and version.anchor_status == "confirmed" and version.tx_hash
            else None
        ),
    )


def main() -> int:
    apply = "--apply" in sys.argv
    with_links = "--with-tx-links" in sys.argv
    store, storage = SupabaseStore(), get_storage()
    totals = {"files": 0, "before": 0, "after": 0, "replaced": 0}
    lock = threading.Lock()

    def shrink(email: str) -> None:
        for version in store.versions_for_email(email):
            document = _document(version, with_links)
            paths: tuple[tuple[Language, str | None], ...] = (
                ("en", version.pdf_en_path),
                ("ka", version.pdf_ka_path),
            )
            for lang, path in paths:
                if not path:
                    continue
                old = storage.get(path)
                new = render_pdf(lang, document)
                before = len(old) if old is not None else 0
                keep = old is not None and len(new) >= before
                if apply and not keep:
                    storage.put(path, new)
                with lock:
                    totals["files"] += 1
                    totals["before"] += before
                    totals["after"] += before if keep else len(new)
                    totals["replaced"] += 1 if apply and not keep else 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(shrink, _emails()))
    mb = 1024 * 1024
    print(f"{totals['files']} stored PDF files")
    print(f"before: {totals['before'] / mb:.1f} MB, after: {totals['after'] / mb:.1f} MB")
    if apply:
        print(f"replaced: {totals['replaced']} files")
    else:
        print("dry run: nothing was changed. Run again with --apply to replace the files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
