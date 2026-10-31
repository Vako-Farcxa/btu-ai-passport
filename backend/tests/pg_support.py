"""A real Postgres for the tests that need one (the sync_student_unit function).

pgserver (a dev dependency) runs a throwaway server in a temp directory. The supabase client
is replaced by PgClient, which runs the few calls the sync store makes as SQL through psql,
so SupabaseSyncStore's own code is what runs, against real tables and the real function.
"""

import json
import re
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from postgrest.exceptions import APIError

from passport_api.sync import SupabaseSyncStore

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
_ERROR = re.compile(r"ERROR:\s+([0-9A-Z]{5}):\s+(.*)")

# What Supabase provides before our migrations run.
_BOOTSTRAP = """
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
create schema storage;
create table storage.buckets (id text primary key, name text, public boolean);
"""


class Database:
    def __init__(self, psql_path: str, uri: str) -> None:
        self._psql = psql_path
        self._uri = uri

    def run(self, sql: str) -> str:
        """Run SQL in one psql session, stop at the first error. Returns stdout."""
        done = subprocess.run(  # noqa: S603
            [
                self._psql,
                self._uri,
                "-X",
                "-q",
                "-A",
                "-t",
                "-v",
                "ON_ERROR_STOP=1",
                "-v",
                "VERBOSITY=verbose",
                "-f",
                "-",
            ],
            input=sql,
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode != 0:
            found = _ERROR.search(done.stderr)
            if found:
                raise APIError({"code": found.group(1), "message": found.group(2)})
            raise RuntimeError(done.stderr)
        return done.stdout.strip()

    def scalar(self, sql: str) -> str:
        return self.run(sql)

    def count(self, table: str) -> int:
        return int(self.run(f"select count(*) from {table}"))

    def json(self, sql: str) -> Any:
        return json.loads(self.run(sql))

    def students_nested(self) -> list[dict[str, Any]]:
        """Students with versions and skill entries nested, as PostgREST would return them."""
        rows: list[dict[str, Any]] = self.json(
            """
            select coalesce(json_agg(row_to_json(s)), '[]'::json) from (
              select st.*, (
                select coalesce(json_agg(row_to_json(v)), '[]'::json) from (
                  select pv.*, (
                    select coalesce(json_agg(row_to_json(e)), '[]'::json)
                    from skill_entries e where e.version_id = pv.id
                  ) as skill_entries
                  from passport_versions pv where pv.student_id = st.id
                ) v
              ) as passport_versions
              from students st
            ) s
            """
        )
        return rows

    def reset(self) -> None:
        self.run(
            "truncate students, passport_versions, skill_entries, source_records, skills "
            "restart identity cascade"
        )


class _Query:
    def __init__(self, db: Database, table: str) -> None:
        self._db = db
        self._table = table
        self._data: Any = None

    def select(self, columns: str) -> "_Query":
        if self._table == "students" and "passport_versions(" in columns:
            self._data = self._db.students_nested()
        else:
            self._data = self._db.json(
                f"select coalesce(json_agg(t), '[]'::json) from (select {columns} "
                f"from {self._table}) t"
            )
        return self

    def upsert(self, rows: list[dict[str, Any]], on_conflict: str) -> "_Query":
        columns = sorted({key for row in rows for key in row})
        updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c != on_conflict)
        payload = json.dumps(rows)
        self._db.run(
            f"insert into {self._table} ({', '.join(columns)}) "
            f"select {', '.join(columns)} from jsonb_populate_recordset(null::{self._table}, "
            f"$pgj${payload}$pgj$::jsonb) "
            f"on conflict ({on_conflict}) do update set {updates}"
        )
        self._data = []
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self._data)


class _Rpc:
    def __init__(self, db: Database, name: str, params: dict[str, Any]) -> None:
        self._db = db
        self._name = name
        self._params = params

    def execute(self) -> SimpleNamespace:
        (value,) = self._params.values()
        payload = json.dumps(value)
        out = self._db.run(f"select {self._name}($pgj${payload}$pgj$::jsonb)")
        return SimpleNamespace(data=json.loads(out))


class PgClient:
    def __init__(self, db: Database) -> None:
        self._db = db

    def table(self, name: str) -> _Query:
        return _Query(self._db, name)

    def rpc(self, name: str, params: dict[str, Any]) -> _Rpc:
        return _Rpc(self._db, name, params)


class PgSyncStore(SupabaseSyncStore):
    """The real SupabaseSyncStore reads and unit writes. Run bookkeeping, PDFs and anchoring
    are not under test here, so they do nothing."""

    def try_acquire(self) -> bool:
        return True

    def record_skipped(self) -> None:
        return None

    def abort(self, error: str = "sheet_unavailable") -> None:
        return None

    def finish(self, rows_read: int, versions_created: int) -> None:
        return None

    def pending_pdfs(self) -> list[Any]:
        return []

    def pending_anchors(self) -> list[Any]:
        return []


def _prepare(db: Database) -> None:
    db.run(_BOOTSTRAP)
    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        # gen_random_uuid() is built into Postgres 13+, so pgcrypto (absent from this build)
        # is not needed to run the tables.
        sql = sql.replace("create extension if not exists pgcrypto;", "")
        db.run(sql)


def start_database(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Database]:
    pgserver = pytest.importorskip("pgserver")
    server = pgserver.get_server(tmp_path_factory.mktemp("pgdata"), cleanup_mode="delete")
    bin_dir = Path(pgserver.postgres_server.POSTGRES_BIN_PATH)
    db = Database(str(bin_dir / "psql"), server.get_uri())
    try:
        _prepare(db)
        yield db
    finally:
        server.cleanup()


Runner = Callable[[str], str]
