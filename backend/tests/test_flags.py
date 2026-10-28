"""Student flags: the student side, the admin side, and the rules between them."""

import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

import passport_api.api.admin as admin_mod
import passport_api.auth as auth
from passport_api.flags import MemoryFlagStore, get_flag_store
from passport_api.main import app

client = TestClient(app)

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_JWK = json.loads(RSAAlgorithm.to_jwk(_KEY.public_key()))
_JWK.update({"kid": "test-key", "alg": "RS256", "use": "sig"})

STUDENT = "demo.student@btu.edu.ge"
OTHER = "error.student@btu.edu.ge"
GOOD = "The Prompt Engineering skill is missing from this version."


def _token(email: str) -> str:
    payload = {
        "aud": "authenticated",
        "iss": "https://test-project.supabase.co/auth/v1",
        "email": email,
        "exp": int(time.time()) + 600,
        "sub": "user",
    }
    return jwt.encode(payload, _KEY, algorithm="RS256", headers={"kid": "test-key"})


def as_student(email: str = STUDENT) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(email)}"}


ADMIN = {"Authorization": "Bearer admin"}


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[MemoryFlagStore]:
    store = MemoryFlagStore()
    app.dependency_overrides[get_flag_store] = lambda: store
    monkeypatch.setattr(auth, "fetch_jwks", lambda: {"keys": [_JWK]})
    monkeypatch.setattr(admin_mod, "require_admin", lambda _auth: "admin@btu.edu.ge")
    yield store
    app.dependency_overrides.clear()


def flag(version: int = 2, comment: str = GOOD, who: str = STUDENT) -> dict[str, object]:
    response = client.post(
        "/flags", headers=as_student(who), json={"version": version, "comment": comment}
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


# -- student: creating -------------------------------------------------------


def test_student_flags_their_own_version() -> None:
    body = flag()
    assert body["version"] == 2
    assert body["status"] == "open"
    assert body["comment"] == GOOD
    assert body["unread"] is False
    # The student never gets the passport id or code back; the server fills them in.
    assert set(body) == {
        "id",
        "version",
        "comment",
        "status",
        "admin_note",
        "created_at",
        "resolved_at",
        "unread",
    }


def test_the_server_records_the_passport_and_code_not_the_client() -> None:
    flag()
    stored = client.get("/admin/flags", headers=ADMIN).json()["flags"][0]
    assert stored["passport_id"] == "BTU-A1B2C3D4E5"
    assert stored["verification_code"] == "A1B2-C3D4-E5F6-G7H8"
    assert stored["student_email"] == STUDENT


def test_ids_cannot_be_sent_by_the_client() -> None:
    response = client.post(
        "/flags",
        headers=as_student(),
        json={"version": 2, "comment": GOOD, "passport_id": "BTU-V2W3X4Y5Z6"},
    )
    assert response.status_code == 422


def test_cannot_flag_someone_elses_version_or_a_missing_one() -> None:
    # error.student has only version 1; demo.student has 1 and 2.
    other = client.post("/flags", headers=as_student(OTHER), json={"version": 2, "comment": GOOD})
    assert other.status_code == 404
    assert other.json() == {"code": "version_not_found"}
    missing = client.post("/flags", headers=as_student(), json={"version": 9, "comment": GOOD})
    assert missing.status_code == 404
    unknown = client.post(
        "/flags", headers=as_student("nobody@btu.edu.ge"), json={"version": 1, "comment": GOOD}
    )
    assert unknown.status_code == 404


@pytest.mark.parametrize(
    "comment",
    ["", "          ", "too short", "x" * 501, "   short   "],
)
def test_comment_must_be_10_to_500_characters_after_trimming(comment: str) -> None:
    response = client.post("/flags", headers=as_student(), json={"version": 2, "comment": comment})
    assert response.status_code == 422
    assert response.json() == {"code": "invalid_comment"}


def test_comment_limits_are_inclusive_and_trimmed() -> None:
    assert flag(1, "  " + "x" * 10 + "  ")["comment"] == "x" * 10
    assert flag(2, "y" * 500)["comment"] == "y" * 500


def test_one_open_flag_per_version() -> None:
    flag()
    again = client.post("/flags", headers=as_student(), json={"version": 2, "comment": GOOD})
    assert again.status_code == 409
    assert again.json() == {"code": "flag_already_open"}
    # Another version is fine.
    flag(1)


def test_a_new_flag_is_allowed_after_the_old_one_is_closed() -> None:
    first = flag()
    done = client.patch(
        f"/admin/flags/{first['id']}",
        headers=ADMIN,
        json={"status": "resolved", "admin_note": "Fixed."},
    )
    assert done.status_code == 200
    flag()


def test_rate_limit_is_five_flags_an_hour_per_student(env: MemoryFlagStore) -> None:
    for number in range(5):
        flag_id = flag(1 + number % 2, f"Problem number {number} with this version.")["id"]
        client.patch(f"/admin/flags/{flag_id}", headers=ADMIN, json={"status": "dismissed"})
    blocked = client.post("/flags", headers=as_student(), json={"version": 2, "comment": GOOD})
    assert blocked.status_code == 429
    assert blocked.json() == {"code": "flag_rate_limited"}
    # It is per student.
    flag(1, GOOD, OTHER)
    # And it is per hour: older flags do not count.
    assert env.count_since(STUDENT, datetime.now(UTC) + timedelta(hours=1)) == 0


def test_student_endpoints_need_a_student_token() -> None:
    assert client.post("/flags", json={"version": 1, "comment": GOOD}).status_code == 401
    assert client.get("/me/flags").status_code == 401
    assert client.post("/me/flags/seen").status_code == 401
    wrong_domain = client.get("/me/flags", headers=as_student("someone@gmail.com"))
    assert wrong_domain.status_code == 403


# -- student: reading and seeing replies --------------------------------------


def test_my_flags_lists_only_my_flags_newest_first() -> None:
    flag(1)
    flag(2)
    flag(1, GOOD, OTHER)
    body = client.get("/me/flags", headers=as_student()).json()
    assert [item["version"] for item in body["flags"]] == [2, 1]
    assert body["unread"] == 0
    other = client.get("/me/flags", headers=as_student(OTHER)).json()
    assert len(other["flags"]) == 1


def test_an_admin_reply_is_unread_until_the_student_opens_it() -> None:
    created = flag()
    assert client.get("/me/flags", headers=as_student()).json()["unread"] == 0
    client.patch(
        f"/admin/flags/{created['id']}",
        headers=ADMIN,
        json={"status": "resolved", "admin_note": "Added the missing skill."},
    )
    before = client.get("/me/flags", headers=as_student()).json()
    assert before["unread"] == 1
    assert before["flags"][0]["unread"] is True
    assert before["flags"][0]["admin_note"] == "Added the missing skill."
    assert before["flags"][0]["resolved_at"] is not None

    seen = client.post("/me/flags/seen", headers=as_student()).json()
    assert seen["unread"] == 0
    assert client.get("/me/flags", headers=as_student()).json()["unread"] == 0


def test_seen_only_marks_my_own_flags() -> None:
    mine = flag()
    theirs = flag(1, GOOD, OTHER)
    for item in (mine, theirs):
        client.patch(f"/admin/flags/{item['id']}", headers=ADMIN, json={"status": "dismissed"})
    client.post("/me/flags/seen", headers=as_student())
    assert client.get("/me/flags", headers=as_student(OTHER)).json()["unread"] == 1


def test_a_changed_reply_is_unread_again() -> None:
    created = flag()
    url = f"/admin/flags/{created['id']}"
    client.patch(url, headers=ADMIN, json={"status": "dismissed", "admin_note": "Not an issue."})
    client.post("/me/flags/seen", headers=as_student())
    client.patch(url, headers=ADMIN, json={"status": "resolved", "admin_note": "Actually fixed."})
    assert client.get("/me/flags", headers=as_student()).json()["unread"] == 1


def test_an_open_flag_is_never_unread() -> None:
    flag()
    assert client.get("/me/flags", headers=as_student()).json()["flags"][0]["unread"] is False


# -- admin ----------------------------------------------------------------------


def test_admin_lists_filters_and_counts_open_flags() -> None:
    first = flag(1)
    flag(2)
    client.patch(f"/admin/flags/{first['id']}", headers=ADMIN, json={"status": "resolved"})
    everything = client.get("/admin/flags", headers=ADMIN).json()
    assert len(everything["flags"]) == 2
    assert everything["open_count"] == 1
    only_open = client.get("/admin/flags?status=open", headers=ADMIN).json()
    assert [f["version"] for f in only_open["flags"]] == [2]
    assert only_open["open_count"] == 1
    resolved = client.get("/admin/flags?status=resolved", headers=ADMIN).json()
    assert [f["version"] for f in resolved["flags"]] == [1]
    assert resolved["open_count"] == 1
    assert client.get("/admin/flags?status=bogus", headers=ADMIN).status_code == 422


def test_admin_resolves_with_a_note_and_is_recorded() -> None:
    created = flag()
    response = client.patch(
        f"/admin/flags/{created['id']}",
        headers=ADMIN,
        json={"status": "resolved", "admin_note": "  Checked the Sheet.  "},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["admin_note"] == "Checked the Sheet."
    assert body["resolved_by"] == "admin@btu.edu.ge"
    assert body["resolved_at"] is not None


def test_admin_update_validates_status_note_and_id() -> None:
    created = flag()
    url = f"/admin/flags/{created['id']}"
    assert client.patch(url, headers=ADMIN, json={"status": "open"}).status_code == 422
    assert client.patch(url, headers=ADMIN, json={"status": "bogus"}).status_code == 422
    long_note = client.patch(
        url, headers=ADMIN, json={"status": "resolved", "admin_note": "n" * 501}
    )
    assert long_note.status_code == 422
    missing = client.patch("/admin/flags/nope", headers=ADMIN, json={"status": "resolved"})
    assert missing.status_code == 404
    assert missing.json() == {"code": "flag_not_found"}


def test_admin_flag_routes_refuse_a_missing_or_student_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.undo()
    monkeypatch.setattr(auth, "fetch_jwks", lambda: {"keys": [_JWK]})
    assert client.get("/admin/flags").status_code == 401
    assert client.patch("/admin/flags/x", json={"status": "resolved"}).status_code == 401
