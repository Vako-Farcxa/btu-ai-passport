from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from passport_api.schemas import Skill

# pending: waiting for the first transaction or its receipt. retrying: a send failed or a stuck
# transaction was replaced, and the reconciler will try again. failed_permanent: the attempt
# cap was reached (or the chain slot is taken by other content), so an admin has to step in.
AnchorStatus = Literal["pending", "retrying", "confirmed", "failed_permanent"]


def normalize_anchor_status(value: str) -> AnchorStatus:
    """Map a stored status to a known one. Legacy "failed" rows were retried every sync, which
    is what "retrying" means now. An unknown value is treated as failed_permanent so it is
    surfaced to an admin instead of being shown as confirmed."""
    if value == "pending":
        return "pending"
    if value == "confirmed":
        return "confirmed"
    if value in ("retrying", "failed"):
        return "retrying"
    return "failed_permanent"


@dataclass(frozen=True)
class StoredVersion:
    passport_id: str
    email: str
    full_name: str
    version: int
    holder_name: str
    verification_code: str
    anchor_status: AnchorStatus
    tx_hash: str | None
    issued_at: str
    skills: tuple[Skill, ...]
    pdf_en_path: str | None = None
    pdf_ka_path: str | None = None
    # When an admin revoked this version, or None.
    version_revoked_at: str | None = None
    # When the student was archived, or None. Archiving revokes every version they hold.
    student_archived_at: str | None = None

    @property
    def revoked_at(self) -> str | None:
        """The earliest of the two dates, or None when the version is in good standing."""
        dates = [d for d in (self.version_revoked_at, self.student_archived_at) if d]
        return min(dates, key=_sort_key) if dates else None


def _sort_key(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


@dataclass(frozen=True)
class LatestVersion:
    """Public facts about a passport's newest version. Never includes its code."""

    version: int
    issued_on: str


class VersionStore(Protocol):
    def find(self, code: str) -> StoredVersion | None: ...

    def max_version(self, passport_id: str) -> int: ...

    def latest_version(self, passport_id: str) -> LatestVersion: ...


class MemoryStore:
    def __init__(self, versions: list[StoredVersion] | tuple[StoredVersion, ...]) -> None:
        self._versions = list(versions)

    def find(self, code: str) -> StoredVersion | None:
        normalized = code.strip().upper()
        for version in self._versions:
            if version.verification_code == normalized:
                return version
        return None

    def max_version(self, passport_id: str) -> int:
        numbers = [
            version.version for version in self._versions if version.passport_id == passport_id
        ]
        if not numbers:
            raise KeyError(passport_id)
        return max(numbers)

    def latest_version(self, passport_id: str) -> LatestVersion:
        versions = [version for version in self._versions if version.passport_id == passport_id]
        if not versions:
            raise KeyError(passport_id)
        newest = max(versions, key=lambda version: version.version)
        return LatestVersion(version=newest.version, issued_on=newest.issued_at[:10])

    def replace_passport(self, passport_id: str, versions: tuple[StoredVersion, ...]) -> None:
        self._versions = [
            version for version in self._versions if version.passport_id != passport_id
        ]
        self._versions.extend(versions)

    def passport_count(self) -> int:
        return len({version.passport_id for version in self._versions})

    def version_count(self) -> int:
        return len(self._versions)

    def versions_for_email(self, email: str) -> tuple[StoredVersion, ...]:
        needle = email.strip().lower()
        return tuple(version for version in self._versions if version.email.lower() == needle)
