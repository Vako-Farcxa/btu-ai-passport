from passport_api.schemas import Skill
from passport_api.store import MemoryStore, StoredVersion

TX_CURRENT = "0x" + "11" * 32
TX_OLDER = "0x" + "22" * 32

DEMO_VERSIONS: tuple[StoredVersion, ...] = (
    StoredVersion(
        passport_id="BTU-A1B2C3D4E5",
        email="demo.student@btu.edu.ge",
        full_name="Nino Beridze",
        version=1,
        holder_name="Nino Beridze",
        verification_code="K9M2-N3P4-Q5R6-S7T8",
        anchor_status="confirmed",
        tx_hash=TX_OLDER,
        issued_at="2025-01-15T00:00:00Z",
        skills=(Skill(skill="Python", badge="Foundation", awarded_on="2025-01-15"),),
    ),
    StoredVersion(
        passport_id="BTU-A1B2C3D4E5",
        email="demo.student@btu.edu.ge",
        full_name="Nino Beridze",
        version=2,
        holder_name="Nino Beridze",
        verification_code="A1B2-C3D4-E5F6-G7H8",
        anchor_status="confirmed",
        tx_hash=TX_CURRENT,
        issued_at="2025-06-01T00:00:00Z",
        skills=(Skill(skill="Machine Learning", badge="Stamp", awarded_on="2025-06-01"),),
    ),
    StoredVersion(
        passport_id="BTU-V2W3X4Y5Z6",
        email="error.student@btu.edu.ge",
        full_name="Giorgi Kapanadze",
        version=1,
        holder_name="Giorgi Kapanadze",
        verification_code="V2W3-X4Y5-Z6A7-B8C9",
        anchor_status="pending",
        tx_hash=None,
        issued_at="2025-03-01T00:00:00Z",
        skills=(Skill(skill="Prompting", badge="", awarded_on=None),),
    ),
)


def apply_demo_seed(store: MemoryStore) -> None:
    """Replace demo passports in place. A second call does not add rows."""
    for passport_id in {version.passport_id for version in DEMO_VERSIONS}:
        versions = tuple(version for version in DEMO_VERSIONS if version.passport_id == passport_id)
        store.replace_passport(passport_id, versions)
