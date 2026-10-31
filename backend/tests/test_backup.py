"""The nightly backup: export, restore, encryption and the workflow that ties them together."""

import csv
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

import passport_api.backup as backup
from passport_api.backup import (
    ADDED_LATER_TABLES,
    SKIPPED_TABLES,
    TABLES,
    BackupError,
    export_database,
    export_sheet,
    export_table,
    read_manifest,
    restore_database,
    restore_sheet,
    write_manifest,
)
from passport_api.settings import Settings, settings

ROOT = Path(__file__).resolve().parents[2]
URL = "https://secret-project.supabase.co"
KEY = "SERVICE-ROLE-KEY-123"


def _rows(table: str, count: int) -> list[dict[str, Any]]:
    # Ids sort the same as plain strings, like the real uuids and "SKL-001" ids do.
    return [
        {"id": f"{table[:3]}-{n:04d}", "name": f"Name {n} \u10d0\u10d1", "tags": ["x"], "n": n}
        for n in range(count)
    ]


class FakeApi:
    """A tiny PostgREST: select * with order=id.asc, limit, id=gt.X and Prefer: count=exact."""

    def __init__(self, data: dict[str, list[dict[str, Any]]], *, cap: int | None = None) -> None:
        self.data = data
        self.cap = cap
        self.requests: list[httpx.Request] = []
        self.posts: list[tuple[str, list[dict[str, Any]], str]] = []
        self.fail_with: int | None = None
        self.lie_about_total: int | None = None

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["apikey"] == KEY
        assert request.headers["authorization"] == f"Bearer {KEY}"
        table = request.url.path.rsplit("/", 1)[1]
        if self.fail_with is not None:
            return httpx.Response(self.fail_with, json={"message": f"secret {KEY} {URL}"})
        if request.method == "POST":
            self.posts.append((table, json.loads(request.content), request.headers["prefer"]))
            return httpx.Response(201)
        params = request.url.params
        rows = [r for r in self.data[table]]
        total = len(rows)
        if "id" in params:
            rows = [r for r in rows if r["id"] > params["id"].removeprefix("gt.")]
        limit = int(params["limit"])
        if self.cap is not None:
            limit = min(limit, self.cap)
        page = rows[:limit]
        shown = total if self.lie_about_total is None else self.lie_about_total
        header = f"0-{max(len(page) - 1, 0)}/{shown}" if page else f"*/{shown}"
        return httpx.Response(200, json=page, headers={"content-range": header})


def _data() -> dict[str, list[dict[str, Any]]]:
    return {table: _rows(table, 5 if table != "flags" else 0) for table in TABLES}


# -- database export -------------------------------------------------------------------


def test_export_writes_one_jsonl_file_per_table(tmp_path: Path) -> None:
    api = FakeApi(_data())
    counts = export_database(tmp_path, URL, KEY, client=api.client())
    assert counts == {table: (0 if table == "flags" else 5) for table in TABLES}
    for table, count in counts.items():
        lines = (tmp_path / "database" / f"{table}.jsonl").read_text(encoding="utf-8").splitlines()
        assert [json.loads(line) for line in lines] == api.data[table]
        assert len(lines) == count


def test_export_reads_every_page_by_id_even_when_the_server_caps_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backup, "PAGE_SIZE", 3)
    api = FakeApi({"students": _rows("students", 10)}, cap=2)
    written = export_table(api.client(), URL, KEY, "students", tmp_path / "s.jsonl")
    assert written == 10
    lines = (tmp_path / "s.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["id"] for line in lines] == [r["id"] for r in api.data["students"]]
    # Keyset paging: every later request asks for ids after the last one seen.
    assert "id" not in api.requests[0].url.params
    assert api.requests[1].url.params["id"] == "gt.stu-0001"
    assert all("offset" not in request.url.params for request in api.requests)
    # Only the first request pays for a count.
    assert api.requests[0].headers["prefer"] == "count=exact"
    assert "prefer" not in api.requests[1].headers


def test_export_fails_when_fewer_rows_arrive_than_the_database_reports(tmp_path: Path) -> None:
    api = FakeApi({"students": _rows("students", 4)})
    api.lie_about_total = 9
    with pytest.raises(BackupError, match="wrote 4 rows but the database has 9"):
        export_table(api.client(), URL, KEY, "students", tmp_path / "s.jsonl")


def test_export_errors_never_contain_the_key_url_or_response_body(tmp_path: Path) -> None:
    api = FakeApi(_data())
    api.fail_with = 401
    with pytest.raises(BackupError) as caught:
        export_database(tmp_path, URL, KEY, client=api.client())
    message = str(caught.value)
    assert message == "table skills: HTTP 401"
    assert KEY not in message and "secret-project" not in message


def test_a_network_error_is_reported_without_the_url(tmp_path: Path) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {URL}", request=request)

    client = httpx.Client(transport=httpx.MockTransport(boom))
    with pytest.raises(BackupError) as caught:
        export_table(client, URL, KEY, "students", tmp_path / "s.jsonl")
    assert "secret-project" not in str(caught.value)
    assert "ConnectError" in str(caught.value)


# -- sheet export and restore ---------------------------------------------------------


class FakeWorksheet:
    def __init__(self, title: str, values: list[list[str]]) -> None:
        self.title = title
        self.values = values
        self.row_count = 2
        self.col_count = 2
        self.cleared = False
        self.updates: list[tuple[list[list[str]], str, str]] = []
        self.resized: tuple[int, int] | None = None

    def get_all_values(self) -> list[list[str]]:
        return self.values

    def clear(self) -> None:
        self.cleared = True

    def resize(self, rows: int, cols: int) -> None:
        self.resized = (rows, cols)

    def update(self, values: list[list[str]], cell: str, value_input_option: str) -> None:
        self.updates.append((values, cell, value_input_option))


class FakeSpreadsheet:
    def __init__(self, sheets: list[FakeWorksheet]) -> None:
        self.sheets = sheets
        self.added: list[FakeWorksheet] = []

    def worksheets(self) -> list[FakeWorksheet]:
        return self.sheets

    def add_worksheet(self, title: str, rows: int, cols: int) -> FakeWorksheet:
        sheet = FakeWorksheet(title, [])
        self.added.append(sheet)
        return sheet


SHEET = [
    FakeWorksheet(
        "Passports",
        [
            ["Email", "Name"],
            ["nino@btu.edu.ge", 'Nino, "Beridze"'],
            ["a@btu.edu.ge", "\u10dc\u10d8\u10dc\u10dd"],
        ],
    ),
    FakeWorksheet("Skills", [["id", "name"], ["SKL-001", "Python"]]),
]


def test_sheet_tabs_become_numbered_csv_files(tmp_path: Path) -> None:
    tabs = export_sheet(tmp_path, FakeSpreadsheet(SHEET))
    assert tabs == {
        "01.csv": {"title": "Passports", "rows": 3},
        "02.csv": {"title": "Skills", "rows": 2},
    }
    with (tmp_path / "sheet" / "01.csv").open(encoding="utf-8", newline="") as handle:
        assert list(csv.reader(handle)) == SHEET[0].values


def test_a_failing_tab_is_reported_by_number_not_by_content(tmp_path: Path) -> None:
    class Broken(FakeWorksheet):
        def get_all_values(self) -> list[list[str]]:
            raise RuntimeError(f"quota exceeded for sheet {URL}")

    with pytest.raises(BackupError) as caught:
        export_sheet(tmp_path, FakeSpreadsheet([Broken("Secret tab name", [])]))
    assert str(caught.value) == "sheet tab 1: read failed (RuntimeError)"


def test_an_empty_spreadsheet_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="no tabs"):
        export_sheet(tmp_path, FakeSpreadsheet([]))


def test_restore_sheet_clears_existing_tabs_and_creates_missing_ones(tmp_path: Path) -> None:
    tabs = export_sheet(tmp_path, FakeSpreadsheet(SHEET))
    write_manifest(tmp_path, database=None, sheet=tabs, errors=[])
    live = FakeWorksheet("Passports", [["old"]])
    spreadsheet = FakeSpreadsheet([live])
    restored = restore_sheet(tmp_path, spreadsheet)
    assert restored == {"Passports": 3, "Skills": 2}
    assert live.cleared
    assert live.resized == (3, 2)
    assert live.updates == [(SHEET[0].values, "A1", "USER_ENTERED")]
    assert [s.title for s in spreadsheet.added] == ["Skills"]
    assert spreadsheet.added[0].updates == [(SHEET[1].values, "A1", "USER_ENTERED")]


# -- database restore and the round trip ----------------------------------------------


def test_restore_upserts_parents_before_children_in_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backup, "RESTORE_BATCH", 2)
    source = FakeApi(_data())
    export_database(tmp_path, URL, KEY, client=source.client())
    target = FakeApi({})
    restored = restore_database(tmp_path, URL, KEY, client=target.client())
    assert restored == {table: (0 if table == "flags" else 5) for table in TABLES}
    order = [table for table, _, _ in target.posts]
    assert order == [t for t in TABLES for _ in range(0 if t == "flags" else 3)]
    assert [t for t in dict.fromkeys(order)] == [t for t in TABLES if t != "flags"]
    assert order.index("students") < order.index("passport_versions") < order.index("skill_entries")
    assert order.index("skills") < order.index("skill_entries")
    assert all(
        prefer == "resolution=merge-duplicates,return=minimal" for _, _, prefer in target.posts
    )
    for table in TABLES:
        sent = [row for t, batch, _ in target.posts if t == table for row in batch]
        assert sent == source.data[table]  # exactly what was exported, Georgian text included


def test_restoring_an_older_backup_skips_tables_added_later(tmp_path: Path) -> None:
    export_database(tmp_path, URL, KEY, client=FakeApi(_data()).client())
    for table in ADDED_LATER_TABLES:
        (tmp_path / "database" / f"{table}.jsonl").unlink()
    target = FakeApi({})
    restored = restore_database(tmp_path, URL, KEY, client=target.client())
    assert set(restored) == {t for t in TABLES if t not in ADDED_LATER_TABLES}
    assert not {table for table, _, _ in target.posts} & set(ADDED_LATER_TABLES)


def test_a_missing_file_for_any_other_table_still_stops_the_restore(tmp_path: Path) -> None:
    export_database(tmp_path, URL, KEY, client=FakeApi(_data()).client())
    (tmp_path / "database" / "students.jsonl").unlink()
    with pytest.raises(BackupError, match="table students: file missing"):
        restore_database(tmp_path, URL, KEY, client=FakeApi({}).client())


def test_restore_can_be_limited_to_some_tables(tmp_path: Path) -> None:
    export_database(tmp_path, URL, KEY, client=FakeApi(_data()).client())
    target = FakeApi({})
    restore_database(tmp_path, URL, KEY, tables=("skills",), client=target.client())
    assert {table for table, _, _ in target.posts} == {"skills"}


def test_restore_reports_a_refusal_without_secrets(tmp_path: Path) -> None:
    export_database(tmp_path, URL, KEY, client=FakeApi(_data()).client())
    target = FakeApi({})
    target.fail_with = 409
    with pytest.raises(BackupError) as caught:
        restore_database(tmp_path, URL, KEY, client=target.client())
    assert str(caught.value) == "table skills: HTTP 409"


def test_restore_refuses_a_folder_that_is_not_a_backup(tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="no manifest.json"):
        read_manifest(tmp_path)
    (tmp_path / "manifest.json").write_text('{"format": 99}')
    with pytest.raises(BackupError, match="unknown backup format"):
        read_manifest(tmp_path)


def test_every_table_the_migrations_create_is_backed_up_or_skipped_on_purpose() -> None:
    created: set[str] = set()
    for path in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        created |= set(
            re.findall(r"create table (?:if not exists )?(?:public\.)?(\w+)", text, re.IGNORECASE)
        )
    assert created == set(TABLES) | set(SKIPPED_TABLES), (
        "A migration created a table that backup.TABLES does not list. Add it (parents before "
        "children), or add it to SKIPPED_TABLES with a reason."
    )
    assert not set(TABLES) & set(SKIPPED_TABLES)


# -- the scripts ----------------------------------------------------------------------


def _script(name: str) -> ModuleType:
    path = ROOT / "backend" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", URL)
    monkeypatch.setattr(settings, "supabase_service_role_key", KEY)
    monkeypatch.setattr(settings, "google_service_account_json", '{"private_key": "PRIVATE-KEY"}')
    monkeypatch.setattr(settings, "sheet_id", "SHEET-ID-999")


def test_backup_script_names_the_missing_settings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _script("backup").main(["--out", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "SUPABASE_SERVICE_ROLE_KEY" in err and "SHEET_ID" in err


def test_backup_script_writes_everything_and_prints_no_secret_or_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = _script("backup")
    _configure(monkeypatch)
    api = FakeApi(_data())
    real_export = script.export_database
    monkeypatch.setattr(
        script,
        "export_database",
        lambda out, url, key: real_export(out, url, key, client=api.client()),
    )
    seen: dict[str, Any] = {}

    def fake_open(timeout: float | None = None, scopes: Any = None) -> FakeSpreadsheet:
        seen.update(timeout=timeout, scopes=scopes)
        return FakeSpreadsheet(SHEET)

    monkeypatch.setattr(script, "open_spreadsheet", fake_open)
    assert script.main(["--out", str(tmp_path / "out")]) == 0
    assert seen["scopes"] == ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["errors"] == []
    assert manifest["database"]["students"] == 5
    assert manifest["sheet"]["01.csv"] == {"title": "Passports", "rows": 3}
    shown = capsys.readouterr()
    text = shown.out + shown.err
    assert "Backup complete." in text
    for secret in (
        KEY,
        URL,
        "secret-project",
        "SHEET-ID-999",
        "PRIVATE-KEY",
        "nino@btu.edu.ge",
        "Name 1",
    ):
        assert secret not in text
        assert secret not in json.dumps(manifest)


def test_one_failing_half_still_saves_the_other_and_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = _script("backup")
    _configure(monkeypatch)
    real_export = script.export_database
    api = FakeApi(_data())
    monkeypatch.setattr(
        script,
        "export_database",
        lambda out, url, key: real_export(out, url, key, client=api.client()),
    )

    def refuse(timeout: float | None = None, scopes: Any = None) -> Any:
        raise script.SheetUnavailableError("sheet_unavailable")

    monkeypatch.setattr(script, "open_spreadsheet", refuse)
    assert script.main(["--out", str(tmp_path)]) == 2
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["errors"] == ["sheet: sheet_unavailable"]
    assert manifest["database"]["students"] == 5
    assert manifest["sheet"] is None
    assert (tmp_path / "database" / "students.jsonl").is_file()
    assert "Backup incomplete" in capsys.readouterr().err


def test_restore_script_is_a_dry_run_unless_told_otherwise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = _script("restore_backup")
    _configure(monkeypatch)
    folder = tmp_path / "b"
    counts = export_database(folder, URL, KEY, client=FakeApi(_data()).client())
    write_manifest(folder, database=counts, sheet=None, errors=[])
    calls: list[str] = []

    def fake_restore(*_args: Any, **_kwargs: Any) -> dict[str, int]:
        calls.append("db")
        return {}

    monkeypatch.setattr(script, "restore_database", fake_restore)
    assert script.main([str(folder), "--database"]) == 0
    assert "Dry run" in capsys.readouterr().out
    assert calls == []
    assert script.main([str(folder)]) == 0
    assert "Nothing selected" in capsys.readouterr().out
    assert script.main([str(folder), "--database", "--yes"]) == 0
    assert calls == ["db"]
    assert script.main([str(tmp_path / "nope")]) == 1


# -- encryption -----------------------------------------------------------------------

SCRIPTS = ROOT / ".github" / "scripts"
needs_openssl = pytest.mark.skipif(
    shutil.which("openssl") is None or shutil.which("bash") is None,
    reason="needs bash and openssl",
)
PASSPHRASE = "correct horse battery staple 42"  # noqa: S105


def _run(
    script: str, *args: Path, passphrase: str | None = PASSPHRASE
) -> subprocess.CompletedProcess[str]:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
    if passphrase is not None:
        env["BACKUP_PASSPHRASE"] = passphrase
    return subprocess.run(  # noqa: S603
        ["bash", str(SCRIPTS / script), *map(str, args)],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        check=False,
        stdin=subprocess.DEVNULL,
    )


@pytest.fixture
def backup_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "backup"
    export_database(folder, URL, KEY, client=FakeApi(_data()).client())
    write_manifest(folder, database={"students": 5}, sheet=None, errors=[])
    return folder


@needs_openssl
def test_encrypt_then_decrypt_gives_the_same_files(tmp_path: Path, backup_folder: Path) -> None:
    encrypted = tmp_path / "b.tar.gz.enc"
    result = _run("encrypt-backup.sh", backup_folder, encrypted)
    assert result.returncode == 0, result.stderr
    assert PASSPHRASE not in result.stdout + result.stderr
    raw = encrypted.read_bytes()
    assert raw.startswith(b"Salted__")
    assert b"students" not in raw and b"manifest" not in raw and "\u10d0".encode() not in raw
    restored = tmp_path / "restored"
    result = _run("decrypt-backup.sh", encrypted, restored)
    assert result.returncode == 0, result.stderr
    for path in backup_folder.rglob("*"):
        if path.is_file():
            assert (restored / path.relative_to(backup_folder)).read_bytes() == path.read_bytes()


@needs_openssl
def test_the_wrong_passphrase_does_not_unpack_anything(tmp_path: Path, backup_folder: Path) -> None:
    encrypted = tmp_path / "b.tar.gz.enc"
    assert _run("encrypt-backup.sh", backup_folder, encrypted).returncode == 0
    result = _run("decrypt-backup.sh", encrypted, tmp_path / "x", passphrase="not the passphrase!!")  # noqa: S106
    assert result.returncode != 0
    assert not (tmp_path / "x" / "manifest.json").exists()


@needs_openssl
def test_encrypting_needs_a_long_passphrase_and_a_real_backup(
    tmp_path: Path, backup_folder: Path
) -> None:
    out = tmp_path / "o.enc"
    assert _run("encrypt-backup.sh", backup_folder, out, passphrase=None).returncode != 0
    assert _run("encrypt-backup.sh", backup_folder, out, passphrase="short").returncode != 0  # noqa: S106
    empty = tmp_path / "empty"
    empty.mkdir()
    assert _run("encrypt-backup.sh", empty, out).returncode != 0


# -- the workflow ---------------------------------------------------------------------

WORKFLOW = (ROOT / ".github" / "workflows" / "backup.yml").read_text(encoding="utf-8")


def test_workflow_runs_nightly_at_0205_tbilisi_and_on_demand() -> None:
    assert re.search(r'^\s+- cron: "5 22 \* \* \*"$', WORKFLOW, re.MULTILINE)  # 22:05 UTC
    assert "workflow_dispatch:" in WORKFLOW


def test_workflow_uploads_only_the_encrypted_file_for_30_days() -> None:
    assert WORKFLOW.count("upload-artifact") == 1
    assert "path: ${{ runner.temp }}/upload/*.enc" in WORKFLOW
    assert "retention-days: 30" in WORKFLOW
    # The readable export is written to a different folder than the one that is uploaded.
    assert '--out "$RUNNER_TEMP/backup"' in WORKFLOW
    assert "/backup" not in WORKFLOW.split("path:")[1].splitlines()[0]


def test_workflow_has_least_privilege_and_never_echoes_secrets() -> None:
    assert re.search(r"^permissions:\n  contents: read$", WORKFLOW, re.MULTILINE)
    for line in WORKFLOW.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "secrets." in stripped:
            # Secrets only ever appear as `NAME: ${{ secrets.NAME }}` environment entries.
            assert re.fullmatch(r"(\w+): \$\{\{ secrets\.\1 \}\}", stripped), stripped
    assert "echo" not in "".join(
        line for line in WORKFLOW.splitlines() if "$SUPABASE" in line or "$BACKUP_PASS" in line
    )
    assert "set -x" not in WORKFLOW


def test_workflow_secret_names_match_what_the_backend_settings_read() -> None:
    names = set(re.findall(r"secrets\.(\w+)", WORKFLOW))
    assert names == {
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "SHEET_ID",
        "BACKUP_PASSPHRASE",
    }
    fields = {name.upper() for name in Settings.model_fields}
    assert names - {"BACKUP_PASSPHRASE"} <= fields
