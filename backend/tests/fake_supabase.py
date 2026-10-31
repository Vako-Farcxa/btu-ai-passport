"""A small in-memory stand-in for the supabase client, for the stores that talk PostgREST.

It supports exactly the calls the app makes on simple tables (select with a plain column list,
insert, update, eq, neq, gte, is_, order, limit, exact count) and it enforces the same unique
rules the migrations do, so a store test fails when the store forgets one. It is not a general
PostgREST: a call it does not know raises, so a new kind of query is noticed instead of ignored.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from postgrest.exceptions import APIError

Row = dict[str, Any]
Defaults = dict[str, Callable[[], Any]]

FLAG_DEFAULTS: Defaults = {
    "id": lambda: str(uuid.uuid4()),
    "status": lambda: "open",
    "admin_note": lambda: "",
    "resolved_by": lambda: None,
    "created_at": lambda: datetime.now(UTC).isoformat(),
    "resolved_at": lambda: None,
    "student_seen_at": lambda: None,
}


class FakeSupabase:
    def __init__(self, defaults: dict[str, Defaults] | None = None) -> None:
        self.tables: dict[str, list[Row]] = {}
        self.defaults = defaults or {"flags": FLAG_DEFAULTS}
        self.calls: list[tuple[str, str]] = []

    def table(self, name: str) -> "Query":
        self.tables.setdefault(name, [])
        return Query(self, name)


class Query:
    def __init__(self, db: FakeSupabase, name: str) -> None:
        self._db = db
        self._name = name
        self._mode = "select"
        self._columns = "*"
        self._count = False
        self._payload: Row = {}
        self._filters: list[Callable[[Row], bool]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    # -- builders -----------------------------------------------------------------------

    def select(self, columns: str = "*", count: object = None) -> "Query":
        if "(" in columns:
            raise NotImplementedError("embedded resources are not supported by the fake")
        self._mode, self._columns, self._count = "select", columns, count is not None
        return self

    def insert(self, row: Row) -> "Query":
        self._mode, self._payload = "insert", dict(row)
        return self

    def update(self, values: Row) -> "Query":
        self._mode, self._payload = "update", dict(values)
        return self

    def eq(self, column: str, value: Any) -> "Query":
        self._filters.append(lambda row: row.get(column) == value)
        return self

    def neq(self, column: str, value: Any) -> "Query":
        self._filters.append(lambda row: row.get(column) != value)
        return self

    def gte(self, column: str, value: Any) -> "Query":
        self._filters.append(lambda row: str(row.get(column)) >= str(value))
        return self

    def is_(self, column: str, value: str) -> "Query":
        if value != "null":
            raise NotImplementedError("only is_(column, 'null') is supported")
        self._filters.append(lambda row: row.get(column) is None)
        return self

    def order(self, column: str, desc: bool = False) -> "Query":
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> "Query":
        self._limit = count
        return self

    # -- running ------------------------------------------------------------------------

    def execute(self) -> Any:
        rows = self._db.tables[self._name]
        self._db.calls.append((self._mode, self._name))
        if self._mode == "insert":
            row = {key: make() for key, make in self._db.defaults.get(self._name, {}).items()}
            row.update(self._payload)
            self._check_unique(rows, row)
            rows.append(row)
            return SimpleNamespace(data=[dict(row)], count=None)
        matching = [row for row in rows if all(test(row) for test in self._filters)]
        if self._mode == "update":
            for row in matching:
                row.update(self._payload)
            return SimpleNamespace(data=[dict(row) for row in matching], count=None)
        if self._order is not None:
            column, desc = self._order
            matching.sort(key=lambda row: str(row.get(column)), reverse=desc)
        total = len(matching)
        if self._limit is not None:
            matching = matching[: self._limit]
        return SimpleNamespace(
            data=[self._project(row) for row in matching], count=total if self._count else None
        )

    def _project(self, row: Row) -> Row:
        if self._columns.strip() == "*":
            return dict(row)
        wanted = [name.strip() for name in self._columns.split(",")]
        return {name: row.get(name) for name in wanted}

    def _check_unique(self, rows: list[Row], new: Row) -> None:
        if self._name == "flags" and any(
            row["passport_id"] == new["passport_id"]
            and row["version"] == new["version"]
            and row["status"] == "open"
            and new["status"] == "open"
            for row in rows
        ):
            raise APIError(
                {
                    "code": "23505",
                    "message": "duplicate key value violates unique constraint "
                    '"flags_one_open_per_version"',
                }
            )
