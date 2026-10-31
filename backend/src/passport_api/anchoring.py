"""Anchor reconciler.

Anchoring a version means sending one transaction to the PassportAnchor contract. On a busy or
flaky testnet that transaction can be slow, dropped, replaced or reverted, so the reconciler is
a small state machine that is run on every sync, from its own endpoint and from the admin
"Retry anchoring" button. One run does this for every unconfirmed version:

1. Check the receipt of every transaction ever sent for it. A mined success confirms it.
2. Read the contract slot. If it already holds this version's hash the work is done (found by
   its log). If it holds anything else the version can never be anchored: failed_permanent.
3. If the last transaction is still in flight and young, wait. If it is stuck in the mempool
   or has vanished, send it again with the same nonce and a higher gas price (a replacement),
   or with a fresh nonce when that nonce was already used by something else.
4. If there is no transaction in flight, send a new one, after the backoff for earlier failures.
5. Count attempts. Past the cap the version becomes failed_permanent and waits for an admin.

A send is only ever made after steps 1 and 2 found the slot empty, so the same hash is never
anchored twice (the contract would revert it with AlreadyAnchored anyway).
"""

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from web3.exceptions import ProviderConnectionError, Web3RPCError

from passport_api.chain import (
    ZERO,
    AnchorChain,
    TxState,
    bumped_gas_price,
    bytes32,
    can_send,
    encode_anchor_call,
)
from passport_api.schemas import AnchorReconcileResult

_log = logging.getLogger(__name__)

ERROR_MAX_LENGTH = 160


@dataclass(frozen=True)
class AnchorPolicy:
    # Sends (and counted failures) allowed before an admin has to step in.
    max_attempts: int = 6
    # A transaction in the mempool for this long is replaced with a higher gas price.
    stuck_after: timedelta = timedelta(minutes=10)
    # A transaction the node does not know at all for this long is sent again.
    dropped_after: timedelta = timedelta(minutes=3)
    backoff_base: timedelta = timedelta(minutes=2)
    backoff_cap: timedelta = timedelta(minutes=60)
    # How long a run keeps polling for receipts of the transactions it just sent, so a new
    # code usually reads as confirmed straight after the sync that created it.
    settle_seconds: float = 20.0
    settle_poll_seconds: float = 2.0
    # How long the run lock is held at most if a run dies without releasing it.
    lock_for: timedelta = timedelta(minutes=5)


DEFAULT_POLICY = AnchorPolicy()


class AnchorRecord(Protocol):
    """The fields of a stored version the reconciler reads and writes."""

    email: str
    version_number: int
    content_hash: str
    verification_id_hash: str
    anchor_status: str
    tx_hash: str | None
    anchored_at: str | None
    anchor_nonce: int | None
    anchor_gas_price: int | None
    anchor_submitted_at: str | None
    anchor_attempts: int
    anchor_last_error: str | None
    anchor_next_attempt_at: str | None
    anchor_tx_hashes: list[str]


class AnchorStore(Protocol):
    def pending_anchors(self) -> Sequence[AnchorRecord]:
        """Versions still to anchor: pending or retrying. Not confirmed, not failed_permanent."""
        ...

    def save_anchor(self, email: str, version_number: int, record: AnchorRecord) -> None: ...

    def try_lock_anchors(self, now: datetime, until: datetime) -> bool:
        """Take the single reconciler lock if it is free or expired at `now`, holding it until
        `until`. False when someone else holds it."""
        ...

    def unlock_anchors(self) -> None: ...


class _Run:
    def __init__(self, now: datetime, policy: AnchorPolicy, force: bool) -> None:
        self.now = now
        self.policy = policy
        self.force = force
        self.next_nonce = 0
        self.sent: list[AnchorRecord] = []
        self.result = AnchorReconcileResult(status="completed")

    def fresh_nonce(self, chain: AnchorChain) -> int:
        # The node's pending count can lag behind transactions sent a moment ago, so keep
        # our own floor for this run.
        return max(chain.pending_nonce(), self.next_nonce)

    def used_nonce(self, nonce: int) -> None:
        self.next_nonce = max(self.next_nonce, nonce + 1)


def reconcile_anchors(
    store: AnchorStore,
    chain: AnchorChain | None,
    *,
    only: Sequence[AnchorRecord] | None = None,
    force: bool = False,
    now: datetime | None = None,
    policy: AnchorPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> AnchorReconcileResult:
    """Bring unconfirmed versions forward. Never raises for chain or RPC trouble.

    only: work on these records instead of everything unconfirmed (the admin retry).
    force: an admin retry. Resets the attempt count and the backoff of the given records and
    lets a failed_permanent one be tried again.
    """
    if chain is None:
        return AnchorReconcileResult(status="no_chain")
    active = policy or DEFAULT_POLICY
    moment = now or datetime.now(UTC)
    if not store.try_lock_anchors(moment, moment + active.lock_for):
        return AnchorReconcileResult(status="skipped", error="anchor_reconcile_in_progress")
    try:
        return _run(store, chain, only, _Run(moment, active, force), sleep, clock)
    finally:
        try:
            store.unlock_anchors()
        except Exception:
            _log.warning("anchor_unlock_failed", exc_info=True)


def _run(
    store: AnchorStore,
    chain: AnchorChain,
    only: Sequence[AnchorRecord] | None,
    run: _Run,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> AnchorReconcileResult:
    result = run.result
    try:
        refusal = can_send(chain)
    except Exception as exc:
        # An RPC outage is not the version's fault: leave every record untouched.
        result.error = error_code(exc)
        return result
    if refusal is not None:
        result.error = refusal
        return result
    records = list(only) if only is not None else list(store.pending_anchors())
    result.checked = len(records)
    for record in records:
        before = _snapshot(record)
        if run.force:
            _reset_for_retry(record)
        outage = False
        try:
            outcome = _process(record, chain, run)
        except Exception as exc:
            code = error_code(exc)
            record.anchor_last_error = code
            outcome = "retrying"
            outage = is_connectivity_error(exc)
            _log.warning("anchor_reconcile_error: %s", code)
        _count(result, outcome)
        if _snapshot(record) != before:
            _save(store, record)
        if outage:
            result.error = "rpc_unreachable"
            break
    if result.error is None:
        _settle(store, chain, run, sleep, clock)
    return result


def _reset_for_retry(record: AnchorRecord) -> None:
    """An admin retry starts the count and the backoff over. Receipts and the contract slot are
    still checked first, so this can never lead to a second anchor of the same hash."""
    if record.anchor_status == "failed_permanent":
        record.anchor_status = "retrying"
    record.anchor_attempts = 0
    record.anchor_next_attempt_at = None


def _count(result: AnchorReconcileResult, outcome: str) -> None:
    if outcome == "confirmed":
        result.confirmed += 1
    elif outcome == "submitted":
        result.submitted += 1
    elif outcome == "replaced":
        result.replaced += 1
    elif outcome == "retrying":
        result.retrying += 1
    elif outcome == "failed_permanent":
        result.failed_permanent += 1
    elif outcome == "waiting":
        result.waiting += 1


def _process(record: AnchorRecord, chain: AnchorChain, run: _Run) -> str:
    if record.anchor_status == "confirmed":
        return "unchanged"
    if record.anchor_status == "failed_permanent" and not run.force:
        return "unchanged"
    now = run.now
    policy = run.policy
    content = bytes32(record.content_hash)
    verification = bytes32(record.verification_id_hash)

    hashes = _known_hashes(record)
    states: dict[str, TxState] = {h: chain.tx_state(h) for h in hashes}
    for tx_hash in reversed(hashes):
        if states[tx_hash] == "success":
            _confirm(record, tx_hash, now)
            return "confirmed"

    stored = chain.stored_content(verification)
    if stored == content:
        # Somebody (an earlier run whose bookkeeping was lost, or a replaced transaction that
        # mined after all) already anchored exactly this hash. Never send it again.
        mined = chain.find_anchor_tx(content, verification)
        if mined is not None:
            _confirm(record, mined, now)
            return "confirmed"
        return _fail(record, "anchored_tx_unknown")
    if stored != ZERO:
        # The slot holds other content, so this version's hash can never be stored there.
        return _fail(record, "slot_conflict")

    last = hashes[-1] if hashes else None
    last_state = states[last] if last is not None else None
    if last_state == "reverted":
        record.anchor_last_error = "reverted"

    replacing = False
    if last_state in ("pending", "missing"):
        submitted = _parse(record.anchor_submitted_at)
        if submitted is None:
            # Old row from before attempts were tracked: start the clock now.
            record.anchor_submitted_at = now.isoformat()
            return "waiting"
        limit = policy.stuck_after if last_state == "pending" else policy.dropped_after
        if now - submitted < limit:
            return "waiting"
        if record.anchor_attempts >= policy.max_attempts:
            return _fail(record, "stuck_max_attempts")
        nonce = record.anchor_nonce
        # Same nonce and a higher price replaces the stuck transaction. If that nonce was
        # already used by a mined transaction there is nothing to replace.
        replacing = nonce is not None and chain.latest_nonce() <= nonce
    elif record.anchor_attempts >= policy.max_attempts:
        return _fail(record, "max_attempts")

    next_attempt = _parse(record.anchor_next_attempt_at)
    if not run.force and next_attempt is not None and now < next_attempt:
        return "waiting"
    return _send(record, chain, run, replacing=replacing)


def _send(record: AnchorRecord, chain: AnchorChain, run: _Run, *, replacing: bool) -> str:
    now = run.now
    nonce = record.anchor_nonce if replacing else None
    floor = None
    if replacing and record.anchor_gas_price:
        floor = bumped_gas_price(record.anchor_gas_price)
    if nonce is None:
        nonce = run.fresh_nonce(chain)
        replacing = False
    try:
        sent = chain.send_anchor(
            encode_anchor_call(record.content_hash, record.verification_id_hash),
            nonce=nonce,
            min_gas_price=floor,
        )
    except Exception as exc:
        code = error_code(exc)
        record.anchor_last_error = code
        record.anchor_status = "retrying"
        if floor is not None:
            # Ask for more next time instead of repeating an offer the node refused.
            record.anchor_gas_price = floor
        if not is_uncounted_error(exc):
            record.anchor_attempts += 1
            if record.anchor_attempts >= run.policy.max_attempts:
                return _fail(record, code)
        record.anchor_next_attempt_at = (now + _backoff(record, run.policy)).isoformat()
        return "retrying"
    record.tx_hash = sent.tx_hash
    record.anchor_nonce = sent.nonce
    record.anchor_gas_price = sent.gas_price
    record.anchor_submitted_at = now.isoformat()
    record.anchor_attempts += 1
    record.anchor_next_attempt_at = None
    if sent.tx_hash not in record.anchor_tx_hashes:
        record.anchor_tx_hashes = [*record.anchor_tx_hashes, sent.tx_hash]
    record.anchor_status = "pending" if record.anchor_attempts == 1 else "retrying"
    run.used_nonce(sent.nonce)
    run.sent.append(record)
    return "replaced" if replacing else "submitted"


def _settle(
    store: AnchorStore,
    chain: AnchorChain,
    run: _Run,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> None:
    """Poll the transactions sent in this run: once straight away, then every few seconds until
    the policy's settle time is used up, so a normal send confirms in the same run."""
    waiting = [r for r in run.sent if r.tx_hash]
    deadline = clock() + run.policy.settle_seconds
    first = True
    while waiting:
        if not first:
            if clock() >= deadline:
                return
            sleep(run.policy.settle_poll_seconds)
        first = False
        still: list[AnchorRecord] = []
        for record in waiting:
            tx_hash = record.tx_hash
            if tx_hash is None:
                continue
            try:
                state = chain.tx_state(tx_hash)
            except Exception:
                return
            if state == "success":
                _confirm(record, tx_hash, run.now)
                _save(store, record)
                run.result.confirmed += 1
            elif state == "reverted":
                record.anchor_last_error = "reverted"
                _save(store, record)
            else:
                still.append(record)
        waiting = still


def _confirm(record: AnchorRecord, tx_hash: str, now: datetime) -> None:
    record.anchor_status = "confirmed"
    record.tx_hash = tx_hash
    record.anchored_at = now.isoformat()
    record.anchor_last_error = None
    record.anchor_next_attempt_at = None
    if tx_hash not in record.anchor_tx_hashes:
        record.anchor_tx_hashes = [*record.anchor_tx_hashes, tx_hash]


def _fail(record: AnchorRecord, code: str) -> str:
    record.anchor_status = "failed_permanent"
    record.anchor_last_error = code
    record.anchor_next_attempt_at = None
    return "failed_permanent"


def _known_hashes(record: AnchorRecord) -> list[str]:
    """Every transaction ever sent for this version, oldest first, current one last."""
    hashes = list(dict.fromkeys(record.anchor_tx_hashes))
    if record.tx_hash:
        if record.tx_hash in hashes:
            hashes.remove(record.tx_hash)
        hashes.append(record.tx_hash)
    return hashes


def _backoff(record: AnchorRecord, policy: AnchorPolicy) -> timedelta:
    steps = max(0, min(record.anchor_attempts, 10))
    return min(policy.backoff_cap, policy.backoff_base * (1 << steps))


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _snapshot(record: AnchorRecord) -> tuple[object, ...]:
    return (
        record.anchor_status,
        record.tx_hash,
        record.anchored_at,
        record.anchor_nonce,
        record.anchor_gas_price,
        record.anchor_submitted_at,
        record.anchor_attempts,
        record.anchor_last_error,
        record.anchor_next_attempt_at,
        tuple(record.anchor_tx_hashes),
    )


def _save(store: AnchorStore, record: AnchorRecord) -> None:
    # The transaction hash must reach the database, or a later run could not tell that this
    # version was already sent. Try twice before giving up.
    try:
        store.save_anchor(record.email, record.version_number, record)
    except Exception:
        _log.warning("anchor_save_retry", exc_info=True)
        store.save_anchor(record.email, record.version_number, record)


def is_connectivity_error(exc: BaseException) -> bool:
    """The node or the network could not be reached (includes HTTP errors and timeouts)."""
    return isinstance(exc, OSError | ProviderConnectionError)


def is_uncounted_error(exc: BaseException) -> bool:
    """Errors that say nothing about the version and are fixed from outside: an unreachable
    RPC, an empty wallet, a gas price spike. They back off but do not use up attempts, so
    funding the wallet or the network recovering heals them without an admin."""
    if is_connectivity_error(exc):
        return True
    return error_code(exc) in {"insufficient_funds", "gas_price_too_high"}


def error_code(exc: BaseException) -> str:
    """A short, safe description for the admin page. Never includes URLs, keys or payloads."""
    if is_connectivity_error(exc):
        return "rpc_unreachable"
    if isinstance(exc, RuntimeError) and str(exc) == "gas_price_too_high":
        return "gas_price_too_high"
    message = _rpc_message(exc).lower()
    for needle, code in (
        ("insufficient funds", "insufficient_funds"),
        ("nonce too low", "nonce_too_low"),
        ("underpriced", "replacement_underpriced"),
        ("already known", "already_known"),
        ("alreadyanchored", "already_anchored"),
    ):
        if needle in message:
            return code
    if message:
        return f"rpc_error: {message[:100]}"
    return type(exc).__name__[:ERROR_MAX_LENGTH]


def _rpc_message(exc: BaseException) -> str:
    if isinstance(exc, Web3RPCError):
        return str(exc.message)
    if isinstance(exc, ValueError) and exc.args and isinstance(exc.args[0], dict):
        return str(exc.args[0].get("message", ""))
    return ""
