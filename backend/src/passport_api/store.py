from dataclasses import dataclass
from typing import Literal, Protocol

from passport_api.schemas import Skill

AnchorStatus = Literal["pending", "confirmed", "failed"]


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


class VersionStore(Protocol):
    def find(self, code: str) -> StoredVersion | None: ...

    def max_version(self, passport_id: str) -> int: ...


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
