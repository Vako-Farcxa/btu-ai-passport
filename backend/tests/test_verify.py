from dataclasses import replace

from fastapi.testclient import TestClient

from passport_api.demo_data import DEMO_VERSIONS, apply_demo_seed
from passport_api.main import app
from passport_api.store import MemoryStore
from passport_api.verify import verify_code

VALID = "A1B2-C3D4-E5F6-G7H8"
OUTDATED = "K9M2-N3P4-Q5R6-S7T8"
PENDING = "V2W3-X4Y5-Z6A7-B8C9"
TX_CURRENT = "11" * 32
TX_OLDER = "22" * 32

client = TestClient(app)


def test_latest_confirmed_code_is_valid() -> None:
    response = client.post("/verify", json={"code": VALID})
    assert response.status_code == 200
    assert response.json() == {
        "outcome": "valid",
        "holder_name": "Nino Beridze",
        "version": 2,
        "is_latest": True,
        "skills": [
            {
                "skill": "Machine Learning",
                "badge": "Stamp",
                "awarded_on": "2025-06-01",
                "description": "",
            },
        ],
        "tx_url": f"https://amoy.polygonscan.com/tx/0x{TX_CURRENT}",
    }


def test_code_match_ignores_case_and_surrounding_spaces() -> None:
    response = client.post("/verify", json={"code": f"  {VALID.lower()}  "})
    assert response.status_code == 200
    assert response.json()["outcome"] == "valid"


def test_internal_space_does_not_match() -> None:
    response = client.post("/verify", json={"code": VALID.replace("-", " -", 1)})
    assert response.status_code == 200
    assert response.json() == {"outcome": "not_found"}


def test_older_confirmed_code_is_outdated() -> None:
    response = client.post("/verify", json={"code": OUTDATED})
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "outdated"
    assert body["is_latest"] is False
    assert body["version"] == 1
    assert body["holder_name"] == "Nino Beridze"
    assert body["skills"] == [
        {"skill": "Python", "badge": "Foundation", "awarded_on": "2025-01-15", "description": ""},
    ]
    assert body["tx_url"] == f"https://amoy.polygonscan.com/tx/0x{TX_OLDER}"


def test_outdated_result_says_which_newer_version_exists_and_when() -> None:
    body = client.post("/verify", json={"code": OUTDATED}).json()
    assert body["latest_version"] == 2
    assert body["latest_issued_at"] == "2025-06-01"


def test_outdated_result_never_contains_the_newer_code() -> None:
    response = client.post("/verify", json={"code": OUTDATED})
    assert VALID not in response.text
    assert "verification_code" not in response.json()


def test_valid_result_has_no_newer_version_fields() -> None:
    body = client.post("/verify", json={"code": VALID}).json()
    assert "latest_version" not in body
    assert "latest_issued_at" not in body


def test_pending_newest_version_still_counts_as_the_newer_version() -> None:
    newer = replace(DEMO_VERSIONS[1], version=3, verification_code="Z9Y8-X7W6-V5U4-T3S2")
    newer = replace(newer, anchor_status="pending", tx_hash=None, issued_at="2026-10-28T08:00:00Z")
    store = MemoryStore([DEMO_VERSIONS[0], DEMO_VERSIONS[1], newer])
    result = verify_code(store, OUTDATED)
    assert result.model_dump()["latest_version"] == 3
    assert result.model_dump()["latest_issued_at"] == "2026-10-28"
    assert "Z9Y8" not in result.model_dump_json()


def test_unknown_code_is_not_found_without_passport_fields() -> None:
    response = client.post("/verify", json={"code": "ZZZZ-ZZZZ-ZZZZ-ZZZZ"})
    assert response.status_code == 200
    assert response.json() == {"outcome": "not_found"}


def test_unconfirmed_anchor_is_error_without_passport_fields() -> None:
    response = client.post("/verify", json={"code": PENDING})
    assert response.status_code == 200
    assert response.json() == {"outcome": "error"}


def test_blank_code_is_not_not_found() -> None:
    response = client.post("/verify", json={"code": "   "})
    assert response.status_code == 422
    assert response.json() == {"code": "code_required"}


def test_applying_demo_seed_twice_keeps_two_passports() -> None:
    store = MemoryStore(())
    apply_demo_seed(store)
    apply_demo_seed(store)
    assert store.passport_count() == 2
    assert store.version_count() == 3


def test_found_payload_hides_email_passport_id_and_code() -> None:
    response = client.post("/verify", json={"code": VALID})
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "valid"
    assert "email" not in body
    assert "passport_id" not in body
    assert "verification_code" not in body


def test_verify_rate_limiting() -> None:
    from passport_api.rate_limit import RateLimiter

    limiter = RateLimiter(max_requests=2, window_seconds=60.0)
    assert limiter.check("1.2.3.4") is True
    assert limiter.check("1.2.3.4") is True
    assert limiter.check("1.2.3.4") is False
    assert limiter.check("5.6.7.8") is True
