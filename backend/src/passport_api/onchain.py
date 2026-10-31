"""Read-only check of a passport version against the PassportAnchor contract.

The public verify endpoint uses this to compare the hash that the contract holds for a
verification code with the hash recomputed from the stored passport. It never signs or sends
anything, so it needs only AMOY_RPC_URL and the contract address, not the issuer key.

Free public RPC nodes are rate limited and sometimes slow, so:

- Every request has a short timeout (ONCHAIN_TIMEOUT_SECONDS, default 3) and is never retried.
- A slot that holds a hash can never change (the contract refuses a second anchor with
  AlreadyAnchored), so a non-empty read is cached for a day. An empty read is cached for a
  minute only, because it normally means "not mined yet".
- After a failed read the RPC is not called again for a short while and every verify in that
  window answers "unavailable" straight away, instead of each waiting out a timeout.

A failure is never reported as verified: the caller gets "unavailable" and shows the database
result with a "check unavailable" badge.
"""

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from eth_typing import HexStr
from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.middleware import ExtraDataToPOAMiddleware

from passport_api.chain import ZERO, contract_abi
from passport_api.settings import settings

_log = logging.getLogger(__name__)

# The BTU PassportAnchor contract on Polygon Amoy. Public: it is listed in the README and
# shown on the verify page so anyone can read it on Polygonscan. ANCHOR_CONTRACT_ADDRESS
# overrides it (local chains, a redeploy).
PUBLISHED_CONTRACT_ADDRESS = "0xf436Ba2A2cd1dc78f1543A1E7e8a9f20B2C40c32"
EXPLORER = "https://amoy.polygonscan.com"

# Contract slots never change once filled, so a filled slot is trusted for a long time.
FILLED_TTL_SECONDS = 24 * 60 * 60
# An empty slot may just not be mined yet, so look again soon.
EMPTY_TTL_SECONDS = 60.0
# After a failed read, leave the RPC alone for this long.
OUTAGE_BACKOFF_SECONDS = 30.0
# A passport anchored this recently may not be visible on every RPC node yet.
FRESH_ANCHOR_GRACE_SECONDS = 120.0
CACHE_ENTRIES = 4096

OnchainStatus = Literal["verified", "mismatch", "missing", "unavailable"]


def contract_address() -> str:
    return Web3.to_checksum_address(settings.anchor_contract_address or PUBLISHED_CONTRACT_ADDRESS)


def contract_url(address: str | None = None) -> str:
    """Polygonscan page where anyone can call the contract's read functions."""
    return f"{EXPLORER}/address/{address or contract_address()}#readContract"


@dataclass(frozen=True)
class OnchainCheck:
    """verified: the contract holds exactly the expected hash. mismatch: it holds another one.
    missing: it holds nothing for this code. unavailable: the chain could not be read."""

    status: OnchainStatus
    block_number: int | None = None


class AnchorReader(Protocol):
    """The read calls the check needs. Raises on any RPC failure."""

    def read_anchor(self, verification_id_hash: bytes) -> bytes: ...

    def block_of(self, tx_hash: str) -> int | None: ...


class Web3AnchorReader:
    def __init__(self, rpc_url: str, address: str, timeout: float) -> None:
        provider = Web3.HTTPProvider(
            rpc_url,
            request_kwargs={"timeout": timeout},
            # No automatic retries: a slow node must not stretch a verify past the timeout.
            exception_retry_configuration=None,
        )
        self._w3 = Web3(provider)
        self._w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self._contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(address), abi=contract_abi()
        )

    def read_anchor(self, verification_id_hash: bytes) -> bytes:
        return bytes(self._contract.functions.anchors(verification_id_hash).call())

    def block_of(self, tx_hash: str) -> int | None:
        try:
            receipt = self._w3.eth.get_transaction_receipt(HexStr(tx_hash))
        except TransactionNotFound:
            return None
        return int(receipt["blockNumber"])


class OnchainVerifier:
    def __init__(
        self,
        reader: AnchorReader,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._reader = reader
        self._clock = clock
        self._lock = threading.Lock()
        self._slots: OrderedDict[bytes, tuple[bytes, float]] = OrderedDict()
        self._blocks: OrderedDict[str, int] = OrderedDict()
        self._down_until = 0.0

    def check(
        self,
        verification_id_hash: bytes,
        expected_content_hash: bytes,
        *,
        tx_hash: str | None = None,
        anchored_age_seconds: float | None = None,
    ) -> OnchainCheck:
        """Compare the contract's hash for this code with the expected one.

        anchored_age_seconds: how long ago the database says it was confirmed, if known. A
        very fresh anchor that reads empty is "unavailable" (a lagging node), not "missing".
        """
        stored = self._stored(verification_id_hash)
        if stored is None:
            return OnchainCheck("unavailable")
        if stored == ZERO:
            fresh = anchored_age_seconds is not None and (
                anchored_age_seconds < FRESH_ANCHOR_GRACE_SECONDS
            )
            return OnchainCheck("unavailable" if fresh else "missing")
        if stored != expected_content_hash:
            return OnchainCheck("mismatch")
        return OnchainCheck("verified", self._block(tx_hash))

    def _stored(self, verification_id_hash: bytes) -> bytes | None:
        now = self._clock()
        with self._lock:
            cached = self._slots.get(verification_id_hash)
            if cached is not None and cached[1] > now:
                return cached[0]
            if self._down_until > now:
                return None
        try:
            stored = self._reader.read_anchor(verification_id_hash)
        except Exception as exc:
            _log.warning("onchain_read_failed: %s", type(exc).__name__)
            with self._lock:
                self._down_until = self._clock() + OUTAGE_BACKOFF_SECONDS
            return None
        ttl = EMPTY_TTL_SECONDS if stored == ZERO else FILLED_TTL_SECONDS
        with self._lock:
            self._slots[verification_id_hash] = (stored, self._clock() + ttl)
            self._slots.move_to_end(verification_id_hash)
            while len(self._slots) > CACHE_ENTRIES:
                self._slots.popitem(last=False)
        return stored

    def _block(self, tx_hash: str | None) -> int | None:
        """Block that mined the anchor transaction. Best effort: None when unknown."""
        if not tx_hash:
            return None
        with self._lock:
            known = self._blocks.get(tx_hash)
            if known is not None:
                return known
            if self._down_until > self._clock():
                return None
        try:
            block = self._reader.block_of(tx_hash)
        except Exception as exc:
            _log.warning("onchain_block_lookup_failed: %s", type(exc).__name__)
            return None
        if block is None:
            return None
        with self._lock:
            self._blocks[tx_hash] = block
            while len(self._blocks) > CACHE_ENTRIES:
                self._blocks.popitem(last=False)
        return block


_verifiers: dict[tuple[str, str, float], OnchainVerifier] = {}
_verifiers_lock = threading.Lock()


def verifier_from_settings() -> OnchainVerifier | None:
    """The shared verifier, or None when the on-chain check is off or has no RPC URL."""
    if not settings.onchain_verify or not settings.amoy_rpc_url:
        return None
    key = (settings.amoy_rpc_url, contract_address(), settings.onchain_timeout_seconds)
    with _verifiers_lock:
        verifier = _verifiers.get(key)
        if verifier is None:
            verifier = OnchainVerifier(Web3AnchorReader(key[0], key[1], key[2]))
            _verifiers[key] = verifier
        return verifier


def clear_verifiers() -> None:
    with _verifiers_lock:
        _verifiers.clear()
