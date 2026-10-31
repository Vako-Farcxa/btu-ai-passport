"""Check a passport against the blockchain without using the BTU website or database.

Give it the verification code and the passport's facts (as printed on the passport). It
recomputes the content hash, reads the hash the contract holds for the code, and compares.

    uv run python scripts/verify_onchain.py --code ABCD-EFGH-IJKL-MNOP --passport passport.json

passport.json:

    {
      "holder_name": "Nino Beridze",
      "passport_id": "BTU-A1B2C3D4E5",
      "version": 2,
      "skills": [{"skill": "Machine Learning", "badge": "Stamp", "awarded_on": "2025-06-01"}]
    }

Needs only a Polygon Amoy RPC URL (a public one is the default) and no key. Exit code 0 means
the contract holds exactly the recomputed hash, 1 means it does not, 2 means the chain could
not be read.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from passport_api.chain import ZERO, bytes32
from passport_api.fingerprint import content_hash, verification_id_hash
from passport_api.onchain import (
    PUBLISHED_CONTRACT_ADDRESS,
    AnchorReader,
    Web3AnchorReader,
    contract_url,
)
from passport_api.schemas import Skill

DEFAULT_RPC = "https://rpc-amoy.polygon.technology"


def check(reader: AnchorReader, code: str, passport: dict[str, object]) -> tuple[int, list[str]]:
    """Returns (exit code, lines to print)."""
    skills = [Skill.model_validate(item) for item in _list(passport["skills"])]
    expected = content_hash(
        holder_name=str(passport["holder_name"]),
        passport_id=str(passport["passport_id"]),
        skills=skills,
        version=int(str(passport["version"])),
    )
    key = verification_id_hash(code)
    lines = [f"verification key : {key}", f"recomputed hash  : {expected}"]
    try:
        stored = reader.read_anchor(bytes32(key))
    except Exception as exc:
        return 2, [*lines, f"could not read the chain: {type(exc).__name__}"]
    lines.append(f"hash on chain    : 0x{stored.hex()}")
    if stored == ZERO:
        return 1, [*lines, "NOT ANCHORED: the contract holds nothing for this code"]
    if stored != bytes32(expected):
        return 1, [*lines, "MISMATCH: the passport does not match the blockchain"]
    return 0, [*lines, "VERIFIED: the contract holds exactly this passport's hash"]


def _list(value: object) -> Sequence[object]:
    if not isinstance(value, list):
        raise SystemExit("passport.json: skills must be a list")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    parser.add_argument("--code", required=True)
    parser.add_argument("--passport", required=True, type=Path)
    parser.add_argument("--rpc", default=DEFAULT_RPC)
    parser.add_argument("--contract", default=PUBLISHED_CONTRACT_ADDRESS)
    args = parser.parse_args()
    passport = json.loads(args.passport.read_text())
    reader = Web3AnchorReader(args.rpc, args.contract, 10.0)
    status, lines = check(reader, args.code, passport)
    print("\n".join(lines))
    print(f"contract         : {contract_url(args.contract)}")
    return status


if __name__ == "__main__":
    sys.exit(main())
