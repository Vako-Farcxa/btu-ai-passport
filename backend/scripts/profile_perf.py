"""Profile the sheet sync against a mock Supabase (PostgREST + Storage) and a mock Google Sheet.

Nothing here touches the network. The mock database is a real HTTP server, so the real
supabase client runs unchanged: connection reuse, request counts and payload sizes are real.
Network cost is modelled with explicit numbers (see the options): every request costs one
round trip, every NEW connection costs two more (TCP + TLS), every Sheets call costs a fixed
latency, and uploads are limited to a bandwidth.

    uv run python scripts/profile_perf.py --students 250 --rtt-ms 60

Prints one table per scenario (steady state, a few changed students, a first import).
"""

import argparse
import json
import re
import socketserver
import statistics
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import gspread.utils

import passport_api.pdf as pdf_mod
import passport_api.sync as sync_mod
from passport_api import db as db_mod
from passport_api.settings import settings

HEADER = [
    "Student ID",
    "BTU Email (Test)",
    "First Name",
    "Last Name",
    "Skill ID",
    "Skill Name",
    "Skill Category",
    "Skill Description",
    "Date Earned",
    "Passport ID (Existing)",
    "Passport Sync Status",
    "Synced Passport Version",
    "Synced At (UTC)",
    "Sync Error / Notes",
]
CATEGORIES = ["AI Skill", "AI Applied Skill", "AI Advanced Skill"]


# --------------------------------------------------------------------------- mock database


@dataclass
class Model:
    students: dict[str, dict[str, Any]] = field(default_factory=dict)
    versions: list[dict[str, Any]] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)
    skills: dict[str, dict[str, Any]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    counter: int = 0

    def nested_students(self) -> list[dict[str, Any]]:
        out = []
        for s in self.students.values():
            out.append(
                {
                    "email": s["email"],
                    "full_name": s["full_name"],
                    "passport_id": s["passport_id"],
                    "deleted_at": None,
                    "passport_versions": [
                        {
                            "version_number": v["version_number"],
                            "skill_fingerprint": v["skill_fingerprint"],
                            "holder_name": v["holder_name"],
                        }
                        for v in self.versions
                        if v["email"] == s["email"]
                    ],
                }
            )
        return out

    def unit(self, p: dict[str, Any]) -> dict[str, Any]:
        email = p["email"]
        created_student = False
        if email not in self.students:
            self.counter += 1
            self.students[email] = {
                "id": f"s{self.counter}",
                "email": email,
                "full_name": p["full_name"],
                "passport_id": p["passport_id"],
            }
            created_student = True
        elif p.get("rename"):
            self.students[email]["full_name"] = p["full_name"]
        version = p.get("version")
        created_version = False
        latest = max(
            (v for v in self.versions if v["email"] == email),
            key=lambda v: v["version_number"],
            default=None,
        )
        if version is not None and (
            latest is None or latest["skill_fingerprint"] != version["skill_fingerprint"]
        ):
            self.versions.append(
                {
                    "email": email,
                    "passport_id": p["passport_id"],
                    "version_number": version["version_number"],
                    "holder_name": version["holder_name"],
                    "verification_code": version["verification_code"],
                    "content_hash": version["content_hash"],
                    "skill_fingerprint": version["skill_fingerprint"],
                    "issued_at": version["issued_at"],
                    "skills": version["skills"],
                    "pdf_en_path": None,
                    "pdf_ka_path": None,
                    "anchor_status": "pending",
                }
            )
            latest = self.versions[-1]
            created_version = True
        for key in p.get("source_keys") or []:
            self.sources.setdefault(key, email)
        stored = [
            {
                "skill": s["skill"],
                "badge": s.get("badge") or "",
                "awarded_on": s.get("awarded_on"),
                "description": s.get("description") or "",
                "skill_id": s.get("skill_id"),
            }
            for s in (latest["skills"] if latest else [])
        ]
        return {
            "student_id": self.students[email]["id"],
            "passport_id": self.students[email]["passport_id"],
            "created_student": created_student,
            "created_version": created_version,
            "version_number": latest["version_number"] if latest else None,
            "holder_name": latest["holder_name"] if latest else None,
            "skills": stored if version is not None else None,
        }


class Stats:
    def __init__(self) -> None:
        self.requests = 0
        self.connections = 0
        self.upload_bytes = 0
        self.by_route: Counter[str] = Counter()
        self.lock = threading.Lock()

    def reset(self) -> None:
        with self.lock:
            self.requests = 0
            self.connections = 0
            self.upload_bytes = 0
            self.by_route.clear()


class Mock(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64

    def __init__(self, model: Model, stats: Stats, rtt: float, bandwidth: float) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.model = model
        self.stats = stats
        self.rtt = rtt
        self.bandwidth = bandwidth
        self.max_rows = 1000  # Supabase default


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: Mock

    def setup(self) -> None:
        super().setup()
        with self.server.stats.lock:
            self.server.stats.connections += 1
        time.sleep(2 * self.server.rtt)  # TCP + TLS handshakes

    def log_message(self, *args: Any) -> None:
        return

    def _send(self, status: int, body: Any, extra: dict[str, str] | None = None) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _handle(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        srv = self.server
        stats = srv.stats
        with stats.lock:
            stats.requests += 1
        time.sleep(srv.rtt)
        url = urlparse(self.path)
        query = parse_qs(url.query)
        path = url.path
        model = srv.model
        route = f"{method} {path.removeprefix('/rest/v1/')}"
        with stats.lock:
            stats.by_route[route] += 1
        if path.startswith("/storage/v1/"):
            with stats.lock:
                stats.upload_bytes += len(raw)
            time.sleep(len(raw) / srv.bandwidth)
            return self._send(200, {"Key": path})
        if path.startswith("/rest/v1/rpc/"):
            name = path.rsplit("/", 1)[1]
            payload = json.loads(raw or b"{}")
            with model.lock:
                if name == "sync_student_unit":
                    return self._send(200, model.unit(payload["p_unit"]))
                if name == "sync_student_units":
                    return self._send(
                        200,
                        [{"ok": True, "result": model.unit(u)} for u in payload["p_units"]],
                    )
                return self._rpc(name, payload)
        table = path.removeprefix("/rest/v1/")
        select = (query.get("select") or [""])[0]
        if method == "POST" and table == "sync_runs":
            return self._send(201, [{"id": "run-1"}])
        if method in ("POST", "PATCH", "DELETE"):
            if method == "PATCH" and table == "passport_versions":
                body = json.loads(raw)
                with model.lock:
                    return self._patch_version(query, body)
            return self._send(200, [])
        if method == "GET":
            with model.lock:
                rows = self._select(table, select, query)
            offset = int((query.get("offset") or ["0"])[0])
            limit = int((query.get("limit") or [str(srv.max_rows)])[0])
            rows = rows[offset : offset + min(limit, srv.max_rows)]
            return self._send(200, rows)
        return self._send(200, [])

    def _rpc(self, name: str, payload: dict[str, Any]) -> None:
        handler = getattr(self.server, "rpc_handlers", {}).get(name)
        if handler is None:
            return self._send(200, [])
        return self._send(200, handler(self.server.model, payload))

    def _patch_version(self, query: dict[str, list[str]], body: dict[str, Any]) -> None:
        sid = (query.get("student_id") or [""])[0].removeprefix("eq.")
        num = int((query.get("version_number") or ["0"])[0].removeprefix("eq."))
        model = self.server.model
        email = next((e for e, s in model.students.items() if s["id"] == sid), None)
        for v in model.versions:
            if v["email"] == email and v["version_number"] == num:
                v.update(body)
        return self._send(200, [])

    def _select(self, table: str, select: str, query: dict[str, list[str]]) -> list[Any]:
        model = self.server.model
        if table == "students":
            email = (query.get("email") or [""])[0].removeprefix("eq.")
            if email:
                s = model.students.get(email)
                return [{"id": s["id"]}] if s else []
            if "passport_versions" in select:
                return model.nested_students()
            return [{"passport_id": s["passport_id"]} for s in model.students.values()]
        if table == "passport_versions":
            if "or" in query:
                out = []
                for v in model.versions:
                    if v["pdf_en_path"] is None or v["pdf_ka_path"] is None:
                        s = model.students[v["email"]]
                        out.append(
                            {
                                "version_number": v["version_number"],
                                "holder_name": v["holder_name"],
                                "verification_code": v["verification_code"],
                                "issued_at": v["issued_at"],
                                "skill_entries": [
                                    {
                                        "skill": k["skill"],
                                        "badge": k.get("badge") or "",
                                        "awarded_on": k.get("awarded_on"),
                                        "description": k.get("description") or "",
                                        "position": i + 1,
                                    }
                                    for i, k in enumerate(v["skills"])
                                ],
                                "students": {
                                    "id": s["id"],
                                    "email": s["email"],
                                    "passport_id": s["passport_id"],
                                },
                            }
                        )
                return out
            if select == "verification_code":
                return [{"verification_code": v["verification_code"]} for v in model.versions]
            if select == "content_hash":
                return [{"content_hash": v["content_hash"]} for v in model.versions]
            return []  # anchors: nothing open (every version is treated as confirmed)
        if table == "source_records":
            return [{"record_key": k} for k in model.sources]
        return []

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_PATCH(self) -> None:
        self._handle("PATCH")

    def do_DELETE(self) -> None:
        self._handle("DELETE")


# --------------------------------------------------------------------------- mock sheet


class FakeWorksheet:
    def __init__(self, sheet: "FakeSpreadsheet", title: str, grid: list[list[str]]) -> None:
        self.sheet = sheet
        self.title = title
        self.grid = grid

    def get_all_values(self) -> list[list[str]]:
        self.sheet.call("get_all_values")
        return [list(r) for r in self.grid]

    def batch_update(self, updates: list[dict[str, Any]], value_input_option: str = "RAW") -> None:
        self.sheet.call("batch_update", cells=len(updates))
        for update in updates:
            row, col = gspread.utils.a1_to_rowcol(update["range"].split("!")[-1])
            while len(self.grid) < row:
                self.grid.append([])
            line = self.grid[row - 1]
            while len(line) < col:
                line.append("")
            line[col - 1] = str(update["values"][0][0])


class FakeSpreadsheet:
    def __init__(self, owner: "FakeSheetService", worksheets: dict[str, FakeWorksheet]) -> None:
        self.owner = owner
        self._sheets = worksheets
        for sheet in worksheets.values():
            sheet.sheet = self

    def call(self, name: str, cells: int = 0) -> None:
        self.owner.call(name, cells)

    def get_worksheet(self, index: int) -> FakeWorksheet:
        self.call("metadata")
        return list(self._sheets.values())[index]

    def worksheet(self, title: str) -> FakeWorksheet:
        self.call("metadata")
        try:
            return self._sheets[title]
        except KeyError:
            raise gspread.WorksheetNotFound(title) from None

    def worksheets(self) -> list[FakeWorksheet]:
        self.call("metadata")
        return list(self._sheets.values())

    def fetch_sheet_metadata(self, params: Any = None) -> dict[str, Any]:
        self.call("metadata")
        return {
            "sheets": [
                {"properties": {"title": t, "index": i, "sheetId": i}}
                for i, t in enumerate(self._sheets)
            ]
        }

    def values_batch_get(self, ranges: Any, params: Any = None) -> dict[str, Any]:
        self.call("values_batch_get")
        out = []
        for r in ranges:
            title = str(r).strip("'")
            if title not in self._sheets:
                raise gspread.exceptions.APIError(_FakeResponse(400, f"Unable to parse range: {r}"))
            out.append({"range": title, "values": [list(x) for x in self._sheets[title].grid]})
        return {"valueRanges": out}


class _FakeResponse:
    def __init__(self, status: int, message: str) -> None:
        self.status_code = status
        self.text = json.dumps({"error": {"code": status, "message": message, "status": "X"}})

    def json(self) -> Any:
        return json.loads(self.text)


class FakeSheetService:
    """What open_spreadsheet() returns. Every Sheets API call costs `latency` seconds."""

    def __init__(self, latency: float, auth: float) -> None:
        self.latency = latency
        self.auth = auth
        self.calls: Counter[str] = Counter()
        self.cells_written = 0
        self.opened = 0
        self.workbook = FakeSpreadsheet(self, {})
        self.lock = threading.Lock()

    def call(self, name: str, cells: int = 0) -> None:
        with self.lock:
            self.calls[name] += 1
            self.cells_written += cells
        time.sleep(self.latency)

    def reset(self) -> None:
        self.calls.clear()
        self.cells_written = 0
        self.opened = 0

    def open(self, timeout: float | None = None, scopes: Any = None) -> FakeSpreadsheet:
        with self.lock:
            self.opened += 1
        time.sleep(self.auth)  # token exchange
        self.call("open_by_key")
        return self.workbook


def build_rows(students: int, per_student: int) -> list[list[str]]:
    rows: list[list[str]] = [["BTU AI Skills Passport: official sheet"], HEADER]
    for i in range(students):
        for j in range(per_student):
            n = (i * per_student + j) % 40
            rows.append(
                [
                    f"S{i:05d}",
                    f"student{i:04d}@btu.edu.ge",
                    "Nino" if i % 2 else "გიორგი",
                    f"Beridze{i}",
                    f"SK-{n:03d}",
                    f"Prompt engineering {n}",
                    CATEGORIES[n % 3],
                    "Writes effective prompts for large language models.",
                    f"2026-0{1 + j % 9}-1{j % 9}",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
    return rows


# --------------------------------------------------------------------------- scenarios


@dataclass
class Result:
    name: str
    seconds: float
    db_requests: int
    db_connections: int
    upload_mb: float
    sheet_calls: int
    sheet_cells: int
    versions_created: int
    top_routes: list[tuple[str, int]]


def run_scenario(
    name: str,
    mock: Mock,
    sheets: FakeSheetService,
    chain: Any,
) -> Result:
    mock.stats.reset()
    sheets.reset()
    sheet = sync_mod.GspreadSheet()
    started = time.perf_counter()
    result = sync_mod.run_sync(sync_mod.SupabaseSyncStore(), sheet, chain)
    elapsed = time.perf_counter() - started
    assert result.status == "completed", result
    return Result(
        name=name,
        seconds=elapsed,
        db_requests=mock.stats.requests,
        db_connections=mock.stats.connections,
        upload_mb=mock.stats.upload_bytes / 1e6,
        sheet_calls=sum(sheets.calls.values()),
        sheet_cells=sheets.cells_written,
        versions_created=result.versions_created,
        top_routes=mock.stats.by_route.most_common(6),
    )


class LatencyChain:
    """FakeChain with a per-call RPC latency."""

    def __init__(self, inner: Any, latency: float) -> None:
        self._inner = inner
        self._latency = latency

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def call(*args: Any, **kwargs: Any) -> Any:
            time.sleep(self._latency)
            return attr(*args, **kwargs)

        return call


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--students", type=int, default=250)
    parser.add_argument("--rows-per-student", type=int, default=3)
    parser.add_argument("--changed", type=int, default=10)
    parser.add_argument("--new", type=int, default=60, help="students added in the last scenario")
    parser.add_argument("--rtt-ms", type=float, default=60.0, help="DB round trip")
    parser.add_argument("--sheets-ms", type=float, default=350.0, help="per Sheets API call")
    parser.add_argument("--sheets-auth-ms", type=float, default=300.0)
    parser.add_argument("--chain-ms", type=float, default=120.0, help="per RPC call")
    parser.add_argument("--upload-mbps", type=float, default=20.0, help="storage upload, Mbit/s")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    from fake_chain import FakeChain

    model = Model()
    stats = Stats()
    # Seed without latency, then switch the latency on for the measured runs.
    mock = Mock(model, stats, 0.0, 1e12)
    threading.Thread(target=mock.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{mock.server_address[1]}"
    settings.supabase_url = url
    settings.supabase_service_role_key = "service-key"
    import tempfile

    settings.pdf_storage_dir = tempfile.mkdtemp()
    clear = getattr(db_mod, "reset_client", None)
    if clear:
        clear()

    sheets = FakeSheetService(0.0, 0.0)
    rows = build_rows(args.students, args.rows_per_student)
    sheets.workbook = FakeSpreadsheet(sheets, {"Sheet1": FakeWorksheet(None, "Sheet1", rows)})  # type: ignore[arg-type]
    chain = LatencyChain(FakeChain(), 0.0)

    results: list[Result] = []
    with patch.object(sync_mod, "open_spreadsheet", sheets.open):
        # first import without latency (this is the seed, not measured)
        run_scenario("seed", mock, sheets, chain)
        mock.rtt = args.rtt_ms / 1000
        mock.bandwidth = args.upload_mbps * 1e6 / 8
        sheets.latency = args.sheets_ms / 1000
        sheets.auth = args.sheets_auth_ms / 1000
        chain._latency = args.chain_ms / 1000
        pdf_mod_storage = pdf_mod  # noqa: F841
        results.append(run_scenario("steady state (nothing changed)", mock, sheets, chain))
        # change `changed` students: a new skill date => new version
        grid = sheets.workbook._sheets["Sheet1"].grid
        for i in range(args.changed):
            idx = 2 + i * args.rows_per_student
            grid[idx][8] = "2026-12-24"
        results.append(
            run_scenario(f"{args.changed} students got a new skill", mock, sheets, chain)
        )
        results.append(run_scenario("steady state again", mock, sheets, chain))
        extra = build_rows(args.students + args.new, args.rows_per_student)[
            2 + args.students * args.rows_per_student :
        ]
        grid.extend(extra)
        results.append(
            run_scenario(f"first import of {args.new} new students", mock, sheets, chain)
        )
    mock.shutdown()

    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2))
        return
    print(
        f"students={args.students} rows={len(rows) - 2} rtt={args.rtt_ms}ms "
        f"sheets={args.sheets_ms}ms upload={args.upload_mbps}Mbps"
    )
    for r in results:
        print(
            f"\n{r.name}: {r.seconds:.1f} s | db requests {r.db_requests} "
            f"(new connections {r.db_connections}) | uploaded {r.upload_mb:.1f} MB | "
            f"sheet calls {r.sheet_calls} (cells written {r.sheet_cells}) | "
            f"versions created {r.versions_created}"
        )
        for route, n in r.top_routes:
            print(f"    {n:5d}  {route}")
    _ = statistics, re, socketserver


if __name__ == "__main__":
    main()
