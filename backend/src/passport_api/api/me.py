from typing import Annotated, Literal

from fastapi import APIRouter, Header
from fastapi.responses import Response

from passport_api.auth import email_from_authorization
from passport_api.demo_data import DEMO_VERSIONS
from passport_api.errors import APIError
from passport_api.pdf import get_storage
from passport_api.schemas import Anchor, Passport, PassportResponse, PassportVersion
from passport_api.settings import settings
from passport_api.store import MemoryStore, StoredVersion
from passport_api.supabase_store import SupabaseStore

router = APIRouter()


def get_store() -> MemoryStore | SupabaseStore:
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseStore()
    return MemoryStore(DEMO_VERSIONS)


def require_active_student(versions: tuple[StoredVersion, ...]) -> None:
    """Refuse an archived student. Archiving revokes the whole passport, so a signed-in
    student who was archived gets a clear 403 instead of any of their data."""
    if any(item.student_archived_at is not None for item in versions):
        raise APIError(403, "passport_revoked")


def ensure_not_archived(email: str) -> None:
    require_active_student(get_store().versions_for_email(email))


def passport_response(versions: tuple[StoredVersion, ...]) -> PassportResponse:
    if not versions:
        return PassportResponse(passport=None)
    passport_id = max(versions, key=lambda item: item.version).passport_id
    own = sorted(
        (item for item in versions if item.passport_id == passport_id),
        key=lambda item: item.version,
        reverse=True,
    )
    current = own[0].version
    return PassportResponse(
        passport=Passport(
            passport_id=passport_id,
            versions=[_version(item, current) for item in own],
        )
    )


def _student_anchor_status(status: str) -> Literal["pending", "confirmed", "failed"]:
    """Students see three states. Retrying is still pending from their side, and only an
    exhausted anchor (an admin has to step in) is shown as failed."""
    if status == "confirmed":
        return "confirmed"
    if status == "failed_permanent":
        return "failed"
    return "pending"


def _version(item: StoredVersion, current: int) -> PassportVersion:
    tx_url = None if item.tx_hash is None else f"https://amoy.polygonscan.com/tx/{item.tx_hash}"
    return PassportVersion(
        version=item.version,
        issued_at=item.issued_at,
        is_current=item.version == current,
        holder_name=item.holder_name,
        verification_code=item.verification_code,
        skills=list(item.skills),
        anchor=Anchor(status=_student_anchor_status(item.anchor_status), tx_url=tx_url),
        revoked_at=item.version_revoked_at,
    )


@router.get("/me/passport", response_model=PassportResponse)
def my_passport(
    authorization: Annotated[str | None, Header()] = None,
) -> PassportResponse:
    email = email_from_authorization(authorization)
    versions = get_store().versions_for_email(email)
    require_active_student(versions)
    return passport_response(versions)


@router.get("/me/passport/versions/{version}/pdf")
def download_passport_pdf(
    version: int,
    lang: Literal["en", "ka"],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    if version < 1:
        raise APIError(404, "version_not_found")
    email = email_from_authorization(authorization)
    versions = get_store().versions_for_email(email)
    require_active_student(versions)
    match = next((item for item in versions if item.version == version), None)
    if match is None:
        raise APIError(404, "version_not_found")
    if match.version_revoked_at is not None:
        raise APIError(403, "version_revoked")
    path = match.pdf_en_path if lang == "en" else match.pdf_ka_path
    if path is None:
        raise APIError(409, "pdf_not_ready")
    data = get_storage().get(path)
    if data is None:
        raise APIError(409, "pdf_not_ready")
    filename = f"{match.passport_id}-v{version}-{lang}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
