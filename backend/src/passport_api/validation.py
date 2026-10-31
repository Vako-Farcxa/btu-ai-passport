"""Input rules for people the admin adds (names and emails). Pure, so they are easy to test.

The same rules live in `frontend/src/lib/validation.ts` for inline messages. This module is
the authority: the API applies it whatever the browser did.
"""

import re
import unicodedata
from typing import Literal

from passport_api.settings import email_domain_allowed

NAME_MIN = 2
NAME_MAX = 50
EMAIL_LOCAL_MIN = 3

# Latin (with accents) and Georgian letters, nothing else. No digits.
_LETTER = "A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u024f\u10a0-\u10c5\u10d0-\u10fa\u10fd-\u10ff"
# Words joined by one space, hyphen or apostrophe. No leading, trailing or doubled joiners.
_NAME = re.compile(rf"^[{_LETTER}]+(?:[ '\u2019-][{_LETTER}]+)*$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

FIRST_NAME_INVALID = "invalid_first_name"
LAST_NAME_INVALID = "invalid_last_name"
INVALID_EMAIL = "invalid_email"
EMAIL_DOMAIN_NOT_ALLOWED = "email_domain_not_allowed"
EMAIL_LOCAL_TOO_SHORT = "email_local_too_short"
EMAIL_LOCAL_NOT_NAME_LIKE = "email_local_not_name_like"
DUPLICATE_EMAIL: Literal["duplicate_email"] = "duplicate_email"


def clean_name(value: str) -> str:
    """NFC, trimmed, inner whitespace runs collapsed to one space."""
    return " ".join(unicodedata.normalize("NFC", value).split())


def name_error(value: str, code: str) -> str | None:
    """`code` when `value` is not a plausible first or last name, else None."""
    name = clean_name(value)
    if not NAME_MIN <= len(name) <= NAME_MAX or not _NAME.match(name):
        return code
    return None


FULL_NAME_INVALID = "invalid_full_name"
PASSPORT_ID_INVALID = "invalid_passport_id"
FULL_NAME_MAX = 2 * NAME_MAX + 1
# A passport ID from the Sheet: capital letters, digits and hyphens, such as BTU-AI-000125.
_PASSPORT_ID = re.compile(r"^[A-Z0-9][A-Z0-9-]{3,39}$")


def full_name_error(value: str) -> str | None:
    """`invalid_full_name` when a name read from the Sheet is not a plausible full name.

    The same letters-only rule the admin form applies to a first and a last name, applied to
    the whole name: at least two characters, at most a 50 character first and last name."""
    name = clean_name(value)
    if not NAME_MIN <= len(name) <= FULL_NAME_MAX or not _NAME.match(name):
        return FULL_NAME_INVALID
    return None


def passport_id_error(value: str) -> str | None:
    """`invalid_passport_id` when an ID typed into the Sheet could not be a passport ID."""
    return None if _PASSPORT_ID.match(value) else PASSPORT_ID_INVALID


def clean_email(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip().lower()


def email_error(value: str) -> str | None:
    """A code for the first rule the (already cleaned) email breaks, else None."""
    if not _EMAIL.match(value):
        return INVALID_EMAIL
    if not email_domain_allowed(value):
        return EMAIL_DOMAIN_NOT_ALLOWED
    local = value.rpartition("@")[0]
    if len(local) < EMAIL_LOCAL_MIN:
        return EMAIL_LOCAL_TOO_SHORT
    if not any(char.isalpha() for char in local):
        return EMAIL_LOCAL_NOT_NAME_LIKE
    return None
