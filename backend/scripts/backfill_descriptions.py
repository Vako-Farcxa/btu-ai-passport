"""Fill skill_entries.description from the live sheet, in place.

Descriptions are not part of the fingerprint or the anchored content hash, so
this creates no new versions and needs no re-anchoring. With --pdfs it also
re-renders the stored PDFs (same paths) so they include the descriptions.
"""

import sys
from typing import Any, cast

from passport_api.db import get_supabase
from passport_api.pdf import PassportPdf, get_storage, publish_pdfs
from passport_api.supabase_store import SupabaseStore
from passport_api.sync import GspreadSheet, _group_rows


def main() -> None:
    groups, _ = _group_rows(GspreadSheet().read_rows())
    wanted = {
        (email, fact.skill, fact.badge, fact.awarded_on): fact.description
        for email, group in groups.items()
        for fact in group.rows
        if fact.description
    }
    rows = cast(
        list[dict[str, Any]],
        get_supabase()
        .table("skill_entries")
        .select("id, skill, badge, awarded_on, description, passport_versions(students(email))")
        .execute()
        .data,
    )
    updated = 0
    for row in rows:
        email = str(row["passport_versions"]["students"]["email"]).lower()
        key = (email, row["skill"], row["badge"], row["awarded_on"])
        text = wanted.get(key)
        if text and text != row["description"]:
            get_supabase().table("skill_entries").update({"description": text}).eq(
                "id", row["id"]
            ).execute()
            updated += 1
    print(f"skill_entries updated: {updated} of {len(rows)}")
    if "--pdfs" not in sys.argv:
        return
    store, storage, rendered = SupabaseStore(), get_storage(), 0
    for email in sorted({key[0] for key in wanted}):
        for version in store.versions_for_email(email):
            if not version.pdf_en_path:
                continue
            publish_pdfs(
                PassportPdf(
                    holder_name=version.holder_name,
                    passport_id=version.passport_id,
                    version=version.version,
                    issued_on=version.issued_at[:10],
                    verification_code=version.verification_code,
                    skills=version.skills,
                ),
                storage,
            )
            rendered += 1
    print(f"pdf versions re-rendered: {rendered}")


if __name__ == "__main__":
    main()
