"""Safe building blocks for admin search filters sent to PostgREST (Supabase)."""

import re

MAX_SEARCH_LENGTH = 100

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def clean_search_term(term: str) -> str:
    """Trim the term and drop characters that can never be part of a name or an email.

    Control characters are removed. `*` is removed because PostgREST treats it as an alias
    of the `%` wildcard and it cannot be escaped.
    """
    return _CONTROL_CHARS.sub("", term).replace("*", "").strip()[:MAX_SEARCH_LENGTH]


def escape_like(term: str) -> str:
    """Make `%`, `_` and `\\` match themselves in a LIKE or ILIKE pattern."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def quote_postgrest_value(value: str) -> str:
    """Wrap a filter value in double quotes so `,` `.` `:` `(` `)` stay plain text."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def contains_filter(columns: list[str], term: str) -> str | None:
    """An `or=(...)` filter body matching `term` anywhere in any column, or None if empty."""
    cleaned = clean_search_term(term)
    if not cleaned:
        return None
    pattern = quote_postgrest_value(f"%{escape_like(cleaned)}%")
    return ",".join(f"{column}.ilike.{pattern}" for column in columns)
