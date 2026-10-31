"""The admin audit log: who changed what, and when.

Every admin write (archive or restore a student, revoke a version, award a skill, edit the
catalog, resolve a flag, run a sync, retry an anchor, rebuild a PDF) adds one row to
`admin_audit` after the change has been saved. A row holds the admin's email, a short action
name, what it was done to, and a few plain facts (no passport content, no tokens).

A failed audit write never undoes or blocks the change that was already saved. It is logged
as an error so it shows up in Render's logs, and the admin sees the change as done.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Protocol

from passport_api.db import get_supabase
from passport_api.schemas import AuditEntry
from passport_api.settings import settings

_log = logging.getLogger(__name__)

Detail = dict[str, str | int | bool | None]
_TARGET_MAX = 200


class AuditStore(Protocol):
    def add(
        self, *, actor: str, action: str, target_type: str, target: str, detail: Detail
    ) -> None: ...

    def recent(self, limit: int) -> list[AuditEntry]: ...


class MemoryAuditStore:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    def add(
        self, *, actor: str, action: str, target_type: str, target: str, detail: Detail
    ) -> None:
        self.entries.append(
            AuditEntry(
                id=str(uuid.uuid4()),
                created_at=datetime.now(UTC),
                actor=actor,
                action=action,
                target_type=target_type,
                target=target,
                detail=detail,
            )
        )

    def recent(self, limit: int) -> list[AuditEntry]:
        return list(reversed(self.entries))[:limit]

    def clear(self) -> None:
        self.entries.clear()


class SupabaseAuditStore:
    def add(
        self, *, actor: str, action: str, target_type: str, target: str, detail: Detail
    ) -> None:
        get_supabase().table("admin_audit").insert(
            {
                "actor": actor,
                "action": action,
                "target_type": target_type,
                "target": target,
                "detail": detail,
            }
        ).execute()

    def recent(self, limit: int) -> list[AuditEntry]:
        response = (
            get_supabase()
            .table("admin_audit")
            .select("id, created_at, actor, action, target_type, target, detail")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = response.data if isinstance(response.data, list) else []
        return [AuditEntry.model_validate(row) for row in rows if isinstance(row, dict)]


memory_store = MemoryAuditStore()


def get_audit_store() -> AuditStore:
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseAuditStore()
    return memory_store


def record_admin_action(
    actor: str,
    action: str,
    *,
    target_type: str = "",
    target: str = "",
    detail: Detail | None = None,
) -> None:
    """Add one row. Never raises: see the module note."""
    try:
        get_audit_store().add(
            actor=actor,
            action=action,
            target_type=target_type,
            target=target[:_TARGET_MAX],
            detail=detail or {},
        )
    except Exception as exc:
        # Only the exception type is logged: a database error can carry row values.
        _log.error("audit_write_failed action=%s error=%s", action, type(exc).__name__)
