import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from passport_api.anchoring import reconcile_anchors
from passport_api.chain import chain_from_settings
from passport_api.errors import APIError
from passport_api.schemas import AnchorReconcileResult, SyncResult
from passport_api.settings import settings
from passport_api.sync import (
    GspreadSheet,
    MemorySyncStore,
    Sheet,
    SupabaseSyncStore,
    SyncStore,
    run_sync,
)

router = APIRouter()


def get_sheet() -> Sheet:
    return GspreadSheet()


def get_sync_store() -> SyncStore:
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseSyncStore()
    return MemorySyncStore()


_sheet_dependency = Depends(get_sheet)
_store_dependency = Depends(get_sync_store)


def _authorized(header: str | None) -> bool:
    expected = settings.sync_token
    if not header or not expected:
        return False
    return secrets.compare_digest(header, expected)


@router.post("/internal/sync")
def run_internal_sync(
    x_sync_token: Annotated[str | None, Header()] = None,
    sheet: Sheet = _sheet_dependency,
    store: SyncStore = _store_dependency,
) -> SyncResult:
    if not _authorized(x_sync_token):
        raise APIError(401, "sync_unauthorized")
    return run_sync(store, sheet)


@router.post("/internal/anchors/reconcile")
def run_anchor_reconcile(
    x_sync_token: Annotated[str | None, Header()] = None,
    store: SyncStore = _store_dependency,
) -> AnchorReconcileResult:
    """Check receipts, confirm mined anchors, replace stuck or dropped transactions and retry
    failures. Guarded like /internal/sync. Safe to call at any time and as often as wanted:
    runs never overlap and nothing is sent twice."""
    if not _authorized(x_sync_token):
        raise APIError(401, "sync_unauthorized")
    return reconcile_anchors(store, chain_from_settings())
