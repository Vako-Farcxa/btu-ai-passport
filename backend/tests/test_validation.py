"""Name and email rules, and how the awards endpoint applies them."""

import pytest

from passport_api.validation import (
    DUPLICATE_EMAIL,
    EMAIL_DOMAIN_NOT_ALLOWED,
    EMAIL_LOCAL_NOT_NAME_LIKE,
    EMAIL_LOCAL_TOO_SHORT,
    FIRST_NAME_INVALID,
    INVALID_EMAIL,
    clean_email,
    clean_name,
    email_error,
    name_error,
)


@pytest.mark.parametrize(
    "name",
    [
        "Nino",
        "Tamar",
        "ნინო",
        "გიორგი",
        "Mary-Jane",
        "O'Brien",
        "O\u2019Neil",
        "Anna Maria",
        "José",
        "Ana  Maria",  # inner whitespace is collapsed, then accepted
        "  Luka  ",
        "ნინო-მარიამ",
        "Ab",
    ],
)
def test_real_names_are_accepted(name: str) -> None:
    assert name_error(name, FIRST_NAME_INVALID) is None


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "1",
        "1 1",
        "A",
        "ა",
        "Nino2",
        "R2D2",
        "123",
        "-Nino",
        "Nino-",
        "Ni--no",
        "Ni''no",
        "Nino!",
        "Nino_Beridze",
        "Nino.",
        "😀😀",
        "A" * 51,
    ],
)
def test_bad_names_are_rejected(name: str) -> None:
    assert name_error(name, FIRST_NAME_INVALID) == FIRST_NAME_INVALID


def test_name_length_limits_apply_after_trimming() -> None:
    assert name_error("  " + "a" * 50 + "  ", FIRST_NAME_INVALID) is None
    assert name_error("a" * 51, FIRST_NAME_INVALID) is not None
    assert clean_name("  Ana \t Maria ") == "Ana Maria"


def test_email_is_lowercased_and_trimmed() -> None:
    assert clean_email("  Nino.Beridze@BTU.edu.ge ") == "nino.beridze@btu.edu.ge"


@pytest.mark.parametrize(
    ("email", "code"),
    [
        ("111@btu.edu.ge", EMAIL_LOCAL_NOT_NAME_LIKE),
        ("12345678@btu.edu.ge", EMAIL_LOCAL_NOT_NAME_LIKE),
        ("1@btu.edu.ge", EMAIL_LOCAL_TOO_SHORT),
        ("ab@btu.edu.ge", EMAIL_LOCAL_TOO_SHORT),
        ("nino@gmail.com", EMAIL_DOMAIN_NOT_ALLOWED),
        ("nino@btu.edu.ge.evil.com", EMAIL_DOMAIN_NOT_ALLOWED),
        ("nino", INVALID_EMAIL),
        ("nino@", INVALID_EMAIL),
        ("@btu.edu.ge", INVALID_EMAIL),
        ("ni no@btu.edu.ge", INVALID_EMAIL),
        ("a@b@btu.edu.ge", INVALID_EMAIL),
        ("", INVALID_EMAIL),
    ],
)
def test_bad_emails_are_rejected(email: str, code: str) -> None:
    assert email_error(clean_email(email)) == code


@pytest.mark.parametrize(
    "email",
    ["nino.beridze@btu.edu.ge", "n.b2@btu.edu.ge", "abc@btu.edu.ge", "user123@btu.edu.ge"],
)
def test_good_emails_are_accepted(email: str) -> None:
    assert email_error(email) is None


def test_duplicate_code_is_stable() -> None:
    assert DUPLICATE_EMAIL == "duplicate_email"
