from passport_api.fingerprint import content_hash, skill_fingerprint, verification_id_hash
from passport_api.schemas import Skill

PYTHON = Skill(skill="Python", badge="Foundation", awarded_on="2025-01-15")
PYTHON_FINGERPRINT = "0x75ced56e3f3271a7826ab26beb3e3f1788c2d1f8b139434bbc5c1193b207607a"
NINO_CONTENT = "0xbe6ae65e59898b3b8488b185e9a1828b4b0402f16eace91f4c7a1a5a2a347b01"
RENAMED_CONTENT = "0x04291233cb672e0908e95217370a783874a823f256943971f34bc14deee4b2ba"
SORTED_FINGERPRINT = "0xd2c04589802155da791d7013baeae9257db5897e545d0865bc1a6263b8ce5bfa"
CODE_HASH = "0x15f843f15aaca4fd05c872d6668236fbcbd1b55e826b9e12a1bdd40f15b298a9"


def test_skill_fingerprint_is_keccak_of_the_ordered_skill_array_only() -> None:
    assert skill_fingerprint([PYTHON]) == PYTHON_FINGERPRINT


def test_content_hash_covers_holder_passport_skills_and_version() -> None:
    hashed = content_hash(
        holder_name="Nino Beridze",
        passport_id="BTU-A1B2C3D4E5",
        skills=[PYTHON],
        version=1,
    )
    renamed = content_hash(
        holder_name="Nino B.",
        passport_id="BTU-A1B2C3D4E5",
        skills=[PYTHON],
        version=1,
    )
    next_version = content_hash(
        holder_name="Nino Beridze",
        passport_id="BTU-A1B2C3D4E5",
        skills=[PYTHON],
        version=2,
    )
    assert hashed == NINO_CONTENT
    assert renamed == RENAMED_CONTENT
    assert next_version != hashed


def test_name_only_change_does_not_change_skill_fingerprint() -> None:
    assert skill_fingerprint([PYTHON]) == PYTHON_FINGERPRINT
    assert content_hash(
        holder_name="Nino Beridze",
        passport_id="BTU-A1B2C3D4E5",
        skills=[PYTHON],
        version=1,
    ) != content_hash(
        holder_name="Nino B.",
        passport_id="BTU-A1B2C3D4E5",
        skills=[PYTHON],
        version=1,
    )


def test_missing_dates_sort_last() -> None:
    unordered = [
        Skill(skill="Alpha", badge="", awarded_on=None),
        Skill(skill="Beta", badge="Stamp", awarded_on="2024-05-01"),
        Skill(skill="Alpha", badge="", awarded_on="2020-01-01"),
    ]
    assert skill_fingerprint(unordered) == SORTED_FINGERPRINT


def test_identical_triples_collapse_to_one_entry() -> None:
    assert skill_fingerprint([PYTHON, PYTHON]) == skill_fingerprint([PYTHON])
    assert skill_fingerprint([PYTHON, PYTHON]) == PYTHON_FINGERPRINT


def test_nfc_and_trimmed_text_hash_the_same() -> None:
    composed = Skill(skill="Café", badge="Stamp", awarded_on=None)
    decomposed = Skill(skill="Cafe\u0301", badge=" Stamp ", awarded_on=None)
    padded = Skill(skill=" Café ", badge="Stamp", awarded_on=None)
    assert skill_fingerprint([decomposed]) == skill_fingerprint([composed])
    assert skill_fingerprint([padded]) == skill_fingerprint([composed])


def test_verification_id_hash_is_keccak_of_the_uppercase_code() -> None:
    assert verification_id_hash("ABCD-EFGH-JKMN-PQRS") == CODE_HASH
    assert verification_id_hash(" abcd-efgh-jkmn-pqrs ") == CODE_HASH
