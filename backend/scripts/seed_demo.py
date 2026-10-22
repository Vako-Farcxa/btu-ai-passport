"""Load the fixed verify fixtures.

When Supabase is configured, passports are upserted by passport id so a second
run does not create another passport. Without Supabase, the API serves the same
fixtures from memory.
"""

import hashlib
from collections.abc import Mapping

from postgrest.types import JSON

from passport_api.demo_data import DEMO_VERSIONS, apply_demo_seed
from passport_api.settings import settings
from passport_api.store import MemoryStore, StoredVersion


def main() -> None:
    store = MemoryStore(())
    apply_demo_seed(store)
    apply_demo_seed(store)
    if settings.supabase_url and settings.supabase_service_role_key:
        _push(DEMO_VERSIONS)
    passports = store.passport_count()
    versions = store.version_count()
    print(f"Demo passports ready: {passports} passports, {versions} versions")


def _push(versions: tuple[StoredVersion, ...]) -> None:
    from passport_api.db import get_supabase

    client = get_supabase()
    passport_ids = {version.passport_id for version in versions}
    for passport_id in passport_ids:
        sample = next(version for version in versions if version.passport_id == passport_id)
        client.table("students").upsert(
            {
                "email": sample.email,
                "full_name": sample.full_name,
                "passport_id": sample.passport_id,
            },
            on_conflict="passport_id",
        ).execute()
    for version in versions:
        student = (
            client.table("students")
            .select("id")
            .eq("passport_id", version.passport_id)
            .limit(1)
            .execute()
        )
        student_id = _required_id(student.data)
        saved = (
            client.table("passport_versions")
            .upsert(
                {
                    "student_id": student_id,
                    "version_number": version.version,
                    "holder_name": version.holder_name,
                    "verification_code": version.verification_code,
                    "verification_id_hash": _fingerprint(version.verification_code),
                    "skill_fingerprint": _fingerprint(
                        f"{version.passport_id}:{version.version}:skills"
                    ),
                    "content_hash": _fingerprint(
                        f"{version.passport_id}:{version.version}:content"
                    ),
                    "anchor_status": version.anchor_status,
                    "tx_hash": version.tx_hash,
                },
                on_conflict="verification_code",
            )
            .execute()
        )
        version_id = _required_id(saved.data)
        client.table("skill_entries").delete().eq("version_id", version_id).execute()
        client.table("skill_entries").insert(
            [
                {
                    "version_id": version_id,
                    "skill": skill.skill,
                    "badge": skill.badge,
                    "awarded_on": skill.awarded_on,
                    "position": index,
                }
                for index, skill in enumerate(version.skills, start=1)
            ]
        ).execute()


def _required_id(rows: list[JSON]) -> str:
    if not rows:
        raise RuntimeError("expected a supabase row")
    row = rows[0]
    if not isinstance(row, Mapping):
        raise RuntimeError("expected a supabase row object")
    row_id = row.get("id")
    if not isinstance(row_id, str):
        raise RuntimeError("expected a string id")
    return row_id


def _fingerprint(value: str) -> str:
    return "0x" + hashlib.sha256(value.encode()).hexdigest()


if __name__ == "__main__":
    main()
