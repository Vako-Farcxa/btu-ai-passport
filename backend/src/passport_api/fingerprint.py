import json
import re
import unicodedata
from collections.abc import Sequence
from datetime import date

from web3 import Web3

from passport_api.schemas import Skill

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def skill_fingerprint(skills: Sequence[Skill]) -> str:
    return _keccak(_dump(_skill_document(skills)))


def content_hash(
    *,
    holder_name: str,
    passport_id: str,
    skills: Sequence[Skill],
    version: int,
) -> str:
    document = {
        "holder_name": _text(holder_name),
        "passport_id": _text(passport_id),
        "skills": _skill_document(skills),
        "version": version,
    }
    return _keccak(_dump(document))


def verification_id_hash(code: str) -> str:
    return _keccak(_text(code).upper())


def normalize_awarded_on(value: str | None) -> str | None:
    return _awarded(value)


def canonical_skills(skills: Sequence[Skill]) -> list[Skill]:
    collapsed: dict[tuple[str, str, str | None], Skill] = {}
    for skill in skills:
        item = Skill(
            skill=_text(skill.skill),
            badge=_text(skill.badge),
            awarded_on=_awarded(skill.awarded_on),
        )
        collapsed[(item.skill, item.badge, item.awarded_on)] = item
    ordered = list(collapsed.values())
    ordered.sort(
        key=lambda item: (item.skill, item.badge, item.awarded_on is None, item.awarded_on or "")
    )
    return ordered


def _skill_document(skills: Sequence[Skill]) -> list[dict[str, str | None]]:
    return [
        {"awarded_on": skill.awarded_on, "badge": skill.badge, "skill": skill.skill}
        for skill in canonical_skills(skills)
    ]


def _awarded(value: str | None) -> str | None:
    if value is None:
        return None
    text = _text(value)
    if _DATE.fullmatch(text) is None:
        return None
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text


def _text(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip()


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _keccak(payload: str) -> str:
    return Web3.keccak(text=payload).to_0x_hex()
