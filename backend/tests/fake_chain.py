"""A tiny in-memory chain for anchoring tests. It behaves like a node: a mempool, mined
transactions, nonces, replacement by gas price, and the contract's one-slot-per-id rule."""

from dataclasses import dataclass

from passport_api.chain import ZERO, SentTx, TxState

ISSUER = "0x1111111111111111111111111111111111111111"


@dataclass
class _Tx:
    nonce: int
    gas_price: int
    content: bytes
    verification: bytes
    state: str  # pending, success, reverted, dropped


class FakeChain:
    def __init__(self, *, auto_mine: bool = True) -> None:
        self.auto_mine = auto_mine
        self.chain_id_value = 80002
        self.issuer = ISSUER
        self.sender = ISSUER
        self.base_gas_price = 30_000_000_000
        self.slots: dict[bytes, bytes] = {}
        self.txs: dict[str, _Tx] = {}
        self.sent: list[SentTx] = []
        self.payloads: list[bytes] = []
        self.send_error: Exception | None = None
        self.rpc_down = False
        self.logs_unavailable = False
        self.mined_nonce = 0
        self._counter = 0

    # --- AnchorChain -------------------------------------------------------------------

    def chain_id(self) -> int:
        self._check_rpc()
        return self.chain_id_value

    def issuer_address(self) -> str:
        return self.issuer

    def sender_address(self) -> str:
        return self.sender

    def stored_content(self, verification_id_hash: bytes) -> bytes:
        self._check_rpc()
        return self.slots.get(verification_id_hash, ZERO)

    def pending_nonce(self) -> int:
        pending = [t.nonce + 1 for t in self.txs.values() if t.state == "pending"]
        return max([self.mined_nonce, *pending])

    def latest_nonce(self) -> int:
        return self.mined_nonce

    def send_anchor(self, data: bytes, *, nonce: int, min_gas_price: int | None = None) -> SentTx:
        self._check_rpc()
        if self.send_error is not None:
            raise self.send_error
        if nonce < self.mined_nonce:
            raise ValueError({"code": -32000, "message": "nonce too low"})
        gas_price = max(self.base_gas_price, min_gas_price or 0)
        for old_hash, old in list(self.txs.items()):
            if old.state == "pending" and old.nonce == nonce:
                if gas_price * 100 < old.gas_price * 110:
                    raise ValueError(
                        {"code": -32000, "message": "replacement transaction underpriced"}
                    )
                old.state = "dropped"  # replaced: the node forgets it
                del self.txs[old_hash]
        self._counter += 1
        tx_hash = "0x" + f"{self._counter:064x}"
        self.txs[tx_hash] = _Tx(nonce, gas_price, data[4:36], data[36:68], "pending")
        sent = SentTx(tx_hash=tx_hash, nonce=nonce, gas_price=gas_price)
        self.sent.append(sent)
        self.payloads.append(data)
        if self.auto_mine:
            self.mine(tx_hash)
        return sent

    def tx_state(self, tx_hash: str) -> TxState:
        self._check_rpc()
        tx = self.txs.get(tx_hash)
        if tx is None or tx.state == "dropped":
            return "missing"
        if tx.state == "success":
            return "success"
        if tx.state == "reverted":
            return "reverted"
        return "pending"

    def find_anchor_tx(self, content_hash: bytes, verification_id_hash: bytes) -> str | None:
        if self.logs_unavailable:
            return None
        for tx_hash, tx in self.txs.items():
            if (
                tx.state == "success"
                and tx.content == content_hash
                and tx.verification == verification_id_hash
            ):
                return tx_hash
        return None

    # --- test controls -----------------------------------------------------------------

    def mine(self, tx_hash: str, *, success: bool = True) -> None:
        tx = self.txs[tx_hash]
        self.mined_nonce = max(self.mined_nonce, tx.nonce + 1)
        if success and self.slots.get(tx.verification, ZERO) == ZERO:
            self.slots[tx.verification] = tx.content
            tx.state = "success"
        else:
            tx.state = "reverted"

    def drop(self, tx_hash: str) -> None:
        """The node forgets a pending transaction (evicted from the mempool)."""
        del self.txs[tx_hash]

    def _check_rpc(self) -> None:
        if self.rpc_down:
            raise ConnectionError("HTTPSConnectionPool(host='rpc.example', port=443): refused")
