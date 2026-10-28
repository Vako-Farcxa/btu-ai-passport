"""Flags: students report a problem with a version of their own passport; admins review.

Nothing here reads or changes a passport, a hash or an anchor.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from passport_api.api.admin import _admin_guard
from passport_api.api.me import get_store
from passport_api.auth import email_from_authorization
from passport_api.errors import APIError
from passport_api.flags import (
    RATE_LIMIT,
    RATE_WINDOW,
    FlagRecord,
    FlagStore,
    clean_comment,
    comment_valid,
    get_flag_store,
    note_valid,
)
from passport_api.schemas import (
    AdminFlag,
    AdminFlagList,
    AdminFlagUpdate,
    FlagCreate,
    FlagStatus,
    StudentFlag,
    StudentFlagList,
)

router = APIRouter(tags=["flags"])
admin_router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(_admin_guard)])

_store_dependency = Depends(get_flag_store)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _student_view(flag: FlagRecord) -> StudentFlag:
    return StudentFlag(
        id=flag.id,
        version=flag.version,
        comment=flag.comment,
        status=flag.status,
        admin_note=flag.admin_note,
        created_at=_parse(flag.created_at),
        resolved_at=None if flag.resolved_at is None else _parse(flag.resolved_at),
        unread=flag.unread,
    )


def _admin_view(flag: FlagRecord) -> AdminFlag:
    return AdminFlag(
        id=flag.id,
        passport_id=flag.passport_id,
        version=flag.version,
        verification_code=flag.verification_code,
        student_email=flag.student_email,
        comment=flag.comment,
        status=flag.status,
        admin_note=flag.admin_note,
        resolved_by=flag.resolved_by,
        created_at=_parse(flag.created_at),
        resolved_at=None if flag.resolved_at is None else _parse(flag.resolved_at),
    )


def _student_list(flags: list[FlagRecord]) -> StudentFlagList:
    return StudentFlagList(
        flags=[_student_view(flag) for flag in flags],
        unread=sum(1 for flag in flags if flag.unread),
    )


# ---------------------------------------------------------------------------
# Student side. Always the signed-in student's own passport.
# ---------------------------------------------------------------------------


@router.post("/flags", response_model=StudentFlag, status_code=201)
def create_flag(
    body: FlagCreate,
    authorization: Annotated[str | None, Header()] = None,
    flags: FlagStore = _store_dependency,
) -> StudentFlag:
    email = email_from_authorization(authorization)
    comment = clean_comment(body.comment)
    if not comment_valid(comment):
        raise APIError(422, "invalid_comment")
    own = next(
        (item for item in get_store().versions_for_email(email) if item.version == body.version),
        None,
    )
    if own is None:
        # Somebody else's version looks exactly like one that does not exist.
        raise APIError(404, "version_not_found")
    if flags.has_open(own.passport_id, own.version):
        raise APIError(409, "flag_already_open")
    if flags.count_since(email, datetime.now(UTC) - RATE_WINDOW) >= RATE_LIMIT:
        raise APIError(429, "flag_rate_limited")
    record = flags.create(
        passport_id=own.passport_id,
        version=own.version,
        verification_code=own.verification_code,
        student_email=email,
        comment=comment,
    )
    return _student_view(record)


@router.get("/me/flags", response_model=StudentFlagList)
def my_flags(
    authorization: Annotated[str | None, Header()] = None,
    flags: FlagStore = _store_dependency,
) -> StudentFlagList:
    email = email_from_authorization(authorization)
    return _student_list(flags.for_student(email))


@router.post("/me/flags/seen", response_model=StudentFlagList)
def mark_my_flags_seen(
    authorization: Annotated[str | None, Header()] = None,
    flags: FlagStore = _store_dependency,
) -> StudentFlagList:
    """The student opened their flags: every admin reply so far counts as read."""
    email = email_from_authorization(authorization)
    flags.mark_seen(email, datetime.now(UTC))
    return _student_list(flags.for_student(email))


# ---------------------------------------------------------------------------
# Admin side (the same guard as every other /admin route)
# ---------------------------------------------------------------------------


@admin_router.get("/flags", response_model=AdminFlagList)
def list_flags(
    status: Annotated[FlagStatus | None, Query()] = None,
    flags: FlagStore = _store_dependency,
) -> AdminFlagList:
    return AdminFlagList(
        flags=[_admin_view(flag) for flag in flags.listing(status)],
        open_count=flags.open_count(),
    )


@admin_router.patch("/flags/{flag_id}", response_model=AdminFlag)
def update_flag(
    flag_id: str,
    body: AdminFlagUpdate,
    admin_email: Annotated[str, Depends(_admin_guard)],
    flags: FlagStore = _store_dependency,
) -> AdminFlag:
    note = clean_comment(body.admin_note)
    if not note_valid(note):
        raise APIError(422, "invalid_comment")
    if flags.get(flag_id) is None:
        raise APIError(404, "flag_not_found")
    updated = flags.close(
        flag_id,
        status=body.status,
        admin_note=note,
        admin_email=admin_email,
        when=datetime.now(UTC),
    )
    if updated is None:
        raise APIError(404, "flag_not_found")
    return _admin_view(updated)
