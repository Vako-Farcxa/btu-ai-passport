"""Deploy PassportAnchor from the issuer wallet and write its artifact.

The API loads backend/assets/PassportAnchor.json. It does not compile Solidity.
"""

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from eth_account import Account
from web3 import Web3

REPO = Path(__file__).resolve().parents[2]
CONTRACT = REPO / "specs" / "001-ai-skills-passport" / "contracts" / "PassportAnchor.sol"
DESTINATION = REPO / "backend" / "assets" / "PassportAnchor.json"


class DeployChain(Protocol):
    def deploy(self, bytecode: str, abi: list[dict[str, object]], sender: str) -> str: ...


def contract_source() -> str:
    return CONTRACT.read_text()


def deploy_and_write(
    *,
    source: str,
    compile_source: Callable[[str], tuple[list[dict[str, object]], str]],
    chain: DeployChain,
    private_key: str,
    destination: Path,
) -> str:
    abi, bytecode = compile_source(source)
    sender = Account.from_key(private_key).address
    address = chain.deploy(bytecode, abi, sender)
    destination.write_text(
        json.dumps(
            {"contractName": "PassportAnchor", "abi": abi, "bytecode": bytecode},
            indent=2,
        )
        + "\n"
    )
    return address


def compile_with_solc(source: str) -> tuple[list[dict[str, object]], str]:
    payload = {
        "language": "Solidity",
        "sources": {"PassportAnchor.sol": {"content": source}},
        "settings": {
            "optimizer": {"enabled": False, "runs": 200},
            "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}},
        },
    }
    solc = shutil.which("solc")
    if solc is None:
        raise RuntimeError("solc_missing")
    completed = subprocess.run(  # noqa: S603
        [solc, "--standard-json"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "solc_failed"
        raise RuntimeError(detail)
    compiled = json.loads(completed.stdout)
    errors = compiled.get("errors")
    if isinstance(errors, list):
        fatal = [
            item for item in errors if isinstance(item, dict) and item.get("severity") == "error"
        ]
        if fatal:
            raise RuntimeError("solc_failed")
    contracts = compiled["contracts"]["PassportAnchor.sol"]["PassportAnchor"]
    bytecode = str(contracts["evm"]["bytecode"]["object"])
    if not bytecode.startswith("0x"):
        bytecode = "0x" + bytecode
    abi = contracts["abi"]
    if not isinstance(abi, list):
        raise RuntimeError("anchor_abi_missing")
    return [cast(dict[str, object], item) for item in abi if isinstance(item, dict)], bytecode


class Web3Deployer:
    def __init__(self, w3: Web3, private_key: str) -> None:
        self._w3 = w3
        self._account = Account.from_key(private_key)

    def deploy(self, bytecode: str, abi: list[dict[str, object]], sender: str) -> str:
        if sender.lower() != self._account.address.lower():
            raise RuntimeError("sender_must_be_issuer")
        contract = self._w3.eth.contract(abi=abi, bytecode=bytecode)
        txn = contract.constructor().build_transaction(
            {
                "from": self._account.address,
                "nonce": self._w3.eth.get_transaction_count(self._account.address),
                "chainId": self._w3.eth.chain_id,
            }
        )
        signed = self._account.sign_transaction(txn)
        sent = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._w3.eth.wait_for_transaction_receipt(sent)
        address = receipt["contractAddress"]
        if not isinstance(address, str) or not address:
            raise RuntimeError("deploy_failed")
        return address


def main() -> None:
    from passport_api.settings import settings

    if not (settings.amoy_rpc_url and settings.btu_issuer_private_key):
        raise SystemExit("Set AMOY_RPC_URL and BTU_ISSUER_PRIVATE_KEY before deploying")
    w3 = Web3(Web3.HTTPProvider(settings.amoy_rpc_url))
    if w3.eth.chain_id != 80002:
        raise SystemExit("expected chain id 80002")
    address = deploy_and_write(
        source=contract_source(),
        compile_source=compile_with_solc,
        chain=Web3Deployer(w3, settings.btu_issuer_private_key),
        private_key=settings.btu_issuer_private_key,
        destination=DESTINATION,
    )
    print(address)


if __name__ == "__main__":
    main()
