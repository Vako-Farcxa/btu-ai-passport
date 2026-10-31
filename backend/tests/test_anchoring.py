"""The anchor reconciler against a fake chain: stuck, dropped, failed and duplicate anchors."""

from datetime import UTC, datetime, timedelta

import pytest
from fake_chain import FakeChain
from web3.exceptions import Web3RPCError

from passport_api.anchoring import AnchorPolicy, AnchorRecord, error_code, reconcile_anchors
from passport_api.chain import GAS_BUMP_PERCENT, bumped_gas_price
from passport_api.schemas import AnchorReconcileResult
from passport_api.sync import MemorySyncStore, VersionRecord

T0 = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
CONTENT = bytes.fromhex("11" * 32)
VERIFICATION = bytes.fromhex("22" * 32)


def _version(number: int = 1, *, status: str = "pending") -> VersionRecord:
    return VersionRecord(
        passport_id="BTU-AI-0001",
        email="ada@btu.edu.ge",
        version_number=number,
        holder_name="Ada Lovelace",
        verification_code="ABCD-EFGH-JKMN-PQR" + str(number),
        verification_id_hash="0x" + f"{0x22 + number - 1:02x}" * 32,
        skill_fingerprint="0x" + f"{number:02x}" * 32,
        content_hash="0x" + f"{0x11 + number - 1:02x}" * 32,
        anchor_status=status,
        pdf_en_path=None,
        pdf_ka_path=None,
        tx_hash=None,
        issued_at="2026-10-31T11:00:00+00:00",
        skills=(),
    )


def _store(*versions: VersionRecord) -> MemorySyncStore:
    store = MemorySyncStore()
    store.versions.extend(versions or (_version(),))
    return store


def _run(
    store: MemorySyncStore,
    chain: FakeChain,
    at: timedelta = timedelta(0),
    **kwargs: object,
) -> AnchorReconcileResult:
    return reconcile_anchors(store, chain, now=T0 + at, **kwargs)  # type: ignore[arg-type]


def test_a_new_version_is_sent_once_and_confirmed() -> None:
    chain = FakeChain()
    store = _store()
    result = _run(store, chain)
    version = store.versions[0]
    assert version.anchor_status == "confirmed"
    assert version.tx_hash == chain.sent[0].tx_hash
    assert version.anchor_attempts == 1
    assert version.anchor_nonce == 0
    assert version.anchor_tx_hashes == [chain.sent[0].tx_hash]
    assert version.anchor_last_error is None
    assert version.anchored_at == T0.isoformat()
    assert (result.submitted, result.confirmed) == (1, 1)
    # Nothing left to do, nothing sent again.
    _run(store, chain, timedelta(minutes=15))
    assert len(chain.sent) == 1


def test_the_tx_hash_is_saved_before_the_receipt_is_awaited() -> None:
    chain = FakeChain(auto_mine=False)
    store = _store()
    saved: list[tuple[str, str | None]] = []
    original = store.save_anchor

    def spy(email: str, number: int, record: AnchorRecord) -> None:
        saved.append((record.anchor_status, record.tx_hash))
        original(email, number, record)

    store.save_anchor = spy  # type: ignore[method-assign,assignment]
    _run(store, chain)
    assert saved[0] == ("pending", chain.sent[0].tx_hash)


def test_a_young_pending_transaction_is_waited_for_not_resent() -> None:
    chain = FakeChain(auto_mine=False)
    store = _store()
    _run(store, chain)
    version = store.versions[0]
    assert version.anchor_status == "pending"
    result = _run(store, chain, timedelta(minutes=5))
    assert len(chain.sent) == 1
    assert result.waiting == 1
    chain.mine(chain.sent[0].tx_hash)
    _run(store, chain, timedelta(minutes=6))
    assert version.anchor_status == "confirmed"
    assert version.tx_hash == chain.sent[0].tx_hash
    assert len(chain.sent) == 1


def test_a_stuck_transaction_is_replaced_with_the_same_nonce_and_a_higher_price() -> None:
    chain = FakeChain(auto_mine=False)
    store = _store()
    _run(store, chain)
    first = chain.sent[0]
    result = _run(store, chain, timedelta(minutes=11))
    assert result.replaced == 1
    second = chain.sent[1]
    assert second.nonce == first.nonce
    assert second.gas_price >= bumped_gas_price(first.gas_price)
    assert second.gas_price >= first.gas_price * (100 + GAS_BUMP_PERCENT) // 100
    version = store.versions[0]
    assert version.anchor_status == "retrying"
    assert version.anchor_attempts == 2
    assert version.tx_hash == second.tx_hash
    assert version.anchor_tx_hashes == [first.tx_hash, second.tx_hash]
    chain.mine(second.tx_hash)
    _run(store, chain, timedelta(minutes=12))
    assert version.anchor_status == "confirmed"
    assert version.tx_hash == second.tx_hash
    assert len(chain.sent) == 2


def test_a_replaced_transaction_that_mines_after_all_is_found_not_duplicated() -> None:
    chain = FakeChain(auto_mine=False)
    store = _store()
    _run(store, chain)
    original = chain.sent[0].tx_hash
    # The replacement is sent, but the node had already included the original.
    tx = chain.txs[original]
    _run(store, chain, timedelta(minutes=11))
    chain.txs[original] = tx
    chain.mine(original)
    _run(store, chain, timedelta(minutes=12))
    version = store.versions[0]
    assert version.anchor_status == "confirmed"
    assert version.tx_hash == original
    assert len(chain.sent) == 2  # no third transaction


def test_a_dropped_transaction_is_resent_after_the_grace_period() -> None:
    chain = FakeChain(auto_mine=False)
    store = _store()
    _run(store, chain)
    chain.drop(chain.sent[0].tx_hash)
    result = _run(store, chain, timedelta(minutes=1))
    assert result.waiting == 1  # the node may just not have gossiped it yet
    assert len(chain.sent) == 1
    _run(store, chain, timedelta(minutes=4))
    assert len(chain.sent) == 2
    assert chain.sent[1].nonce == chain.sent[0].nonce
    assert store.versions[0].anchor_status == "retrying"


def test_a_dropped_transaction_whose_nonce_was_used_gets_a_fresh_nonce() -> None:
    chain = FakeChain(auto_mine=False)
    store = _store()
    _run(store, chain)
    chain.drop(chain.sent[0].tx_hash)
    chain.mined_nonce = 1  # something else from the same wallet took nonce 0
    _run(store, chain, timedelta(minutes=4))
    assert chain.sent[1].nonce == 1


def test_a_reverted_transaction_is_sent_again_and_counted() -> None:
    chain = FakeChain(auto_mine=False)
    store = _store()
    _run(store, chain)
    chain.mine(chain.sent[0].tx_hash, success=False)
    _run(store, chain, timedelta(minutes=1))
    version = store.versions[0]
    assert version.anchor_last_error == "reverted"
    assert version.anchor_attempts == 2
    assert chain.sent[1].nonce == 1
    chain.mine(chain.sent[1].tx_hash)
    _run(store, chain, timedelta(minutes=2))
    assert version.anchor_status == "confirmed"
    assert version.anchor_last_error is None


def test_a_failed_send_backs_off_then_retries() -> None:
    chain = FakeChain()
    chain.send_error = ValueError({"code": -32000, "message": "execution reverted: boom"})
    store = _store()
    result = _run(store, chain)
    version = store.versions[0]
    assert result.retrying == 1
    assert version.anchor_status == "retrying"
    assert version.anchor_attempts == 1
    assert version.anchor_last_error == "rpc_error: execution reverted: boom"
    assert version.anchor_next_attempt_at == (T0 + timedelta(minutes=4)).isoformat()
    chain.send_error = None
    result = _run(store, chain, timedelta(minutes=1))
    assert result.waiting == 1
    assert chain.sent == []
    _run(store, chain, timedelta(minutes=5))
    assert version.anchor_status == "confirmed"
    assert version.anchor_attempts == 2


def test_backoff_doubles_up_to_the_cap() -> None:
    chain = FakeChain()
    chain.send_error = ValueError({"message": "boom"})
    store = _store()
    gaps: list[timedelta] = []
    moment = timedelta(0)
    for _ in range(5):
        _run(store, chain, moment)
        due = datetime.fromisoformat(str(store.versions[0].anchor_next_attempt_at))
        gaps.append(due - (T0 + moment))
        moment = due - T0
    assert gaps == [timedelta(minutes=m) for m in (4, 8, 16, 32, 60)]


def test_the_attempt_cap_ends_in_failed_permanent_and_stops_trying() -> None:
    chain = FakeChain()
    chain.send_error = ValueError({"message": "boom"})
    store = _store()
    moment = timedelta(0)
    for _ in range(6):
        _run(store, chain, moment)
        moment += timedelta(hours=2)
    version = store.versions[0]
    assert version.anchor_status == "failed_permanent"
    assert version.anchor_attempts == 6
    assert version.anchor_last_error == "rpc_error: boom"
    chain.send_error = None
    result = _run(store, chain, moment)
    assert result.checked == 0  # no longer in the work list
    assert chain.sent == []


def test_a_stuck_transaction_also_ends_in_failed_permanent() -> None:
    chain = FakeChain(auto_mine=False)
    store = _store()
    moment = timedelta(0)
    for _ in range(12):
        _run(store, chain, moment)
        moment += timedelta(minutes=11)
    version = store.versions[0]
    assert version.anchor_status == "failed_permanent"
    assert version.anchor_last_error == "stuck_max_attempts"
    assert len(chain.sent) == 6


def test_an_admin_retry_resets_the_cap_and_finishes_the_job() -> None:
    chain = FakeChain()
    chain.send_error = ValueError({"message": "boom"})
    store = _store()
    moment = timedelta(0)
    for _ in range(6):
        _run(store, chain, moment)
        moment += timedelta(hours=2)
    version = store.versions[0]
    assert version.anchor_status == "failed_permanent"
    chain.send_error = None
    # What the admin endpoint does: run only this record, forced.
    result = _run(store, chain, moment, only=[version], force=True)
    assert result.confirmed == 1
    assert version.anchor_status == "confirmed"


def test_rpc_outages_and_an_empty_wallet_do_not_use_up_attempts() -> None:
    chain = FakeChain()
    store = _store()
    moment = timedelta(0)
    for error in (
        ConnectionError("down"),
        TimeoutError("slow"),
        ValueError({"message": "insufficient funds for gas * price + value"}),
    ):
        chain.send_error = error
        for _ in range(8):
            _run(store, chain, moment)
            moment += timedelta(hours=2)
        version = store.versions[0]
        assert version.anchor_status == "retrying"
        assert version.anchor_attempts == 0
    assert version.anchor_last_error == "insufficient_funds"
    chain.send_error = None
    _run(store, chain, moment)
    assert version.anchor_status == "confirmed"
    assert version.anchor_attempts == 1


def test_an_unreachable_rpc_leaves_every_record_untouched() -> None:
    chain = FakeChain()
    chain.rpc_down = True
    store = _store(_version(1), _version(2))
    result = _run(store, chain)
    assert result.error == "rpc_unreachable"
    assert chain.sent == []
    assert [v.anchor_status for v in store.versions] == ["pending", "pending"]
    assert [v.anchor_attempts for v in store.versions] == [0, 0]
    # The lock is released, so the next run can go.
    chain.rpc_down = False
    assert _run(store, chain, timedelta(minutes=1)).confirmed == 2


def test_an_rpc_dropping_mid_run_stops_the_run_without_burning_attempts() -> None:
    chain = FakeChain(auto_mine=False)
    store = _store(_version(1), _version(2))
    _run(store, chain)
    chain.rpc_down = True
    # The chain id answers (cached by the provider) but the receipt lookup fails.
    original = chain.chain_id
    chain.chain_id = lambda: 80002  # type: ignore[method-assign]
    result = _run(store, chain, timedelta(minutes=30))
    chain.chain_id = original  # type: ignore[method-assign]
    assert result.error == "rpc_unreachable"
    assert store.versions[0].anchor_last_error == "rpc_unreachable"
    assert [v.anchor_attempts for v in store.versions] == [1, 1]


def test_an_already_anchored_hash_is_confirmed_from_the_contract_and_never_sent() -> None:
    chain = FakeChain()
    store = _store()
    version = store.versions[0]
    # An earlier run sent it, the process died before saving the hash, and it mined.
    chain.slots[bytes.fromhex(version.verification_id_hash[2:])] = bytes.fromhex(
        version.content_hash[2:]
    )
    chain.base_gas_price = 1
    hash_in_logs = "0x" + "ee" * 32
    chain.find_anchor_tx = lambda *_: hash_in_logs  # type: ignore[method-assign]
    result = _run(store, chain)
    assert chain.sent == []
    assert result.confirmed == 1
    assert version.anchor_status == "confirmed"
    assert version.tx_hash == hash_in_logs


def test_an_anchored_hash_with_no_findable_transaction_is_flagged_not_resent() -> None:
    chain = FakeChain()
    store = _store()
    version = store.versions[0]
    chain.slots[bytes.fromhex(version.verification_id_hash[2:])] = bytes.fromhex(
        version.content_hash[2:]
    )
    chain.logs_unavailable = True
    _run(store, chain)
    assert chain.sent == []
    assert version.anchor_status == "failed_permanent"
    assert version.anchor_last_error == "anchored_tx_unknown"


def test_a_slot_holding_other_content_is_permanent_and_nothing_is_sent() -> None:
    chain = FakeChain()
    store = _store()
    version = store.versions[0]
    chain.slots[bytes.fromhex(version.verification_id_hash[2:])] = bytes.fromhex("99" * 32)
    result = _run(store, chain)
    assert chain.sent == []
    assert result.failed_permanent == 1
    assert version.anchor_status == "failed_permanent"
    assert version.anchor_last_error == "slot_conflict"


def test_two_versions_in_one_run_use_distinct_nonces() -> None:
    chain = FakeChain(auto_mine=False)
    store = _store(_version(1), _version(2), _version(3))
    _run(store, chain)
    assert [sent.nonce for sent in chain.sent] == [0, 1, 2]


def test_a_node_that_lags_on_the_pending_count_cannot_cause_a_nonce_clash() -> None:
    chain = FakeChain(auto_mine=False)
    chain.pending_nonce = lambda: 0  # type: ignore[method-assign]
    store = _store(_version(1), _version(2))
    _run(store, chain)
    assert [sent.nonce for sent in chain.sent] == [0, 1]


def test_a_replacement_the_node_refuses_asks_for_more_next_time() -> None:
    chain = FakeChain(auto_mine=False)
    store = _store()
    _run(store, chain)
    first = chain.sent[0]
    chain.base_gas_price = first.gas_price
    # A node that wants a 30 percent bump: the default 25 percent offer is refused.
    original_send = chain.send_anchor

    def strict(data: bytes, *, nonce: int, min_gas_price: int | None = None):  # type: ignore[no-untyped-def]
        if min_gas_price is not None and min_gas_price < first.gas_price * 130 // 100:
            raise ValueError({"message": "replacement transaction underpriced"})
        return original_send(data, nonce=nonce, min_gas_price=min_gas_price)

    chain.send_anchor = strict  # type: ignore[method-assign]
    _run(store, chain, timedelta(minutes=11))
    version = store.versions[0]
    assert version.anchor_last_error == "replacement_underpriced"
    assert len(chain.sent) == 1
    _run(store, chain, timedelta(minutes=40))
    assert len(chain.sent) == 2
    assert chain.sent[1].gas_price >= first.gas_price * 130 // 100


def test_a_pending_row_from_before_tracking_starts_its_timer_instead_of_resending() -> None:
    chain = FakeChain(auto_mine=False)
    store = _store()
    version = store.versions[0]
    chain.send_anchor(b"\x00" * 4 + CONTENT + VERIFICATION, nonce=0)
    version.tx_hash = chain.sent[0].tx_hash
    version.anchor_status = "pending"
    _run(store, chain)
    assert len(chain.sent) == 1
    assert version.anchor_submitted_at == T0.isoformat()


def test_a_run_never_overlaps_another() -> None:
    chain = FakeChain()
    store = _store()
    assert store.try_lock_anchors(T0, T0 + timedelta(minutes=5))
    result = _run(store, chain, timedelta(minutes=1))
    assert result.status == "skipped"
    assert chain.sent == []
    # A lock left behind by a dead run expires.
    result = _run(store, chain, timedelta(minutes=6))
    assert result.status == "completed"
    assert store.versions[0].anchor_status == "confirmed"


def test_the_lock_is_released_even_when_a_run_blows_up() -> None:
    chain = FakeChain()
    store = _store()
    store.pending_anchors = lambda: (_ for _ in ()).throw(RuntimeError("db down"))  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        _run(store, chain)
    assert store.try_lock_anchors(T0, T0 + timedelta(minutes=1))


def test_without_a_configured_chain_nothing_happens() -> None:
    store = _store()
    result = reconcile_anchors(store, None, now=T0)
    assert result.status == "no_chain"
    assert store.versions[0].anchor_status == "pending"


def test_error_text_never_leaks_urls_keys_or_payloads() -> None:
    rpc_url = "https://polygon-amoy.g.alchemy.com/v2/SUPERSECRETKEY"
    chain = FakeChain()
    chain.send_error = RuntimeError(f"failed calling {rpc_url} with key 0xdeadbeef")
    store = _store()
    _run(store, chain)
    error = store.versions[0].anchor_last_error or ""
    assert "SUPERSECRET" not in error and "alchemy" not in error and "deadbeef" not in error
    assert error == "RuntimeError"
    chain.send_error = ConnectionError(f"HTTPSConnectionPool(host='{rpc_url}')")
    assert error_code(chain.send_error) == "rpc_unreachable"


def test_node_errors_become_short_codes() -> None:
    assert error_code(ValueError({"message": "nonce too low: next nonce 5"})) == "nonce_too_low"
    assert error_code(ValueError({"message": "already known"})) == "already_known"
    assert error_code(RuntimeError("gas_price_too_high")) == "gas_price_too_high"
    assert error_code(Web3RPCError("insufficient funds for gas")) == "insufficient_funds"
    assert error_code(Web3RPCError("odd failure")) == "rpc_error: odd failure"
    long = ValueError({"message": "x" * 500})
    assert len(error_code(long)) <= 120


def test_a_gas_price_spike_waits_without_using_attempts() -> None:
    chain = FakeChain()
    chain.send_error = RuntimeError("gas_price_too_high")
    store = _store()
    _run(store, chain)
    version = store.versions[0]
    assert version.anchor_last_error == "gas_price_too_high"
    assert version.anchor_attempts == 0
    assert version.anchor_status == "retrying"


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_the_run_polls_briefly_for_the_receipt_of_what_it_sent() -> None:
    chain = FakeChain(auto_mine=False)
    store = _store()
    timer = _Clock()
    original = chain.tx_state
    calls = {"n": 0}

    def mined_on_third_lookup(tx_hash: str):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 3:
            chain.mine(tx_hash)
        return original(tx_hash)

    chain.tx_state = mined_on_third_lookup  # type: ignore[method-assign]
    policy = AnchorPolicy(settle_seconds=20, settle_poll_seconds=2)
    result = reconcile_anchors(
        store, chain, now=T0, policy=policy, sleep=timer.sleep, clock=timer.clock
    )
    assert store.versions[0].anchor_status == "confirmed"
    assert result.confirmed == 1
    assert timer.sleeps == [2, 2]


def test_the_polling_stops_at_the_time_limit() -> None:
    chain = FakeChain(auto_mine=False)
    store = _store()
    timer = _Clock()
    policy = AnchorPolicy(settle_seconds=7, settle_poll_seconds=2)
    reconcile_anchors(store, chain, now=T0, policy=policy, sleep=timer.sleep, clock=timer.clock)
    assert sum(timer.sleeps) <= 8
    assert store.versions[0].anchor_status == "pending"
