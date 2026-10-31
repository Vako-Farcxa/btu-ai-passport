"""Time the admin dashboard and the passport page against a mock Supabase.

The real FastAPI app runs under uvicorn and the real supabase client talks HTTP to a mock
PostgREST that costs one round trip per request (and two more per NEW connection). Browser
requests are issued the way the pages issue them: in parallel, after the admin check.

    uv run python scripts/profile_api.py --rtt-ms 60
"""

import argparse
import json
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import uvicorn

sys.path.insert(0, os.path.dirname(__file__))
import profile_perf as pp  # noqa: E402

from passport_api import auth as auth_mod  # noqa: E402
from passport_api.settings import settings  # noqa: E402

ADMIN = "admin@btu.edu.ge"
STUDENT = "student0007@btu.edu.ge"


def make_students(n: int) -> list[dict[str, Any]]:
    rows = []
    for i in range(n):
        rows.append(
            {
                "id": f"00000000-0000-0000-0000-{i:012d}",
                "email": f"student{i:04d}@btu.edu.ge",
                "full_name": f"Student {i}",
                "passport_id": f"BTU-{i:010d}",
                "admin_managed": i % 10 == 0,
                "deleted_at": None,
                "created_at": "2026-10-01T10:00:00+00:00",
                "passport_versions": [
                    {"version_number": v + 1, "anchor_status": "confirmed"}
                    for v in range(1 + i % 3)
                ],
            }
        )
    return rows


def my_student() -> dict[str, Any]:
    versions = []
    for v in range(5):
        versions.append(
            {
                "version_number": v + 1,
                "holder_name": "Student 7",
                "verification_code": f"AAAA-BBBB-CCCC-{v:04d}",
                "anchor_status": "confirmed",
                "tx_hash": "0x" + "ab" * 32,
                "issued_at": "2026-10-01T10:00:00+00:00",
                "pdf_en_path": "x/en.pdf",
                "pdf_ka_path": "x/ka.pdf",
                "revoked_at": None,
                "content_hash": "0x" + "cd" * 32,
                "anchored_at": "2026-10-01T10:05:00+00:00",
                "skill_entries": [
                    {
                        "skill": f"Skill {k}",
                        "badge": "BDG-AI-001",
                        "awarded_on": "2026-01-01",
                        "description": "Writes effective prompts " * 4,
                        "position": k + 1,
                    }
                    for k in range(3 + v * 2)
                ],
            }
        )
    return {
        "email": STUDENT,
        "full_name": "Student 7",
        "passport_id": "BTU-0000000007",
        "deleted_at": None,
        "passport_versions": versions,
    }


class ApiHandler(pp._Handler):
    def _handle(self, method: str) -> None:  # type: ignore[override]
        url = urlparse(self.path)
        query = parse_qs(url.query)
        path = url.path
        srv = self.server
        if not path.startswith("/rest/v1/"):
            return super()._handle(method)
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length) if length else b""
        with srv.stats.lock:
            srv.stats.requests += 1
            route = f"{method} {path.removeprefix('/rest/v1/')}"
            srv.stats.by_route[route] += 1
        time.sleep(srv.rtt)
        table = path.removeprefix("/rest/v1/")
        select = (query.get("select") or [""])[0]
        data = srv.data
        headers: dict[str, str] = {}
        rows: Any = []
        if table.startswith("rpc/"):
            name = table[4:]
            fn = srv.rpcs.get(name)
            if fn is None:
                return self._send(
                    404,
                    {
                        "code": "PGRST202",
                        "message": "Could not find the function",
                        "details": None,
                        "hint": None,
                    },
                )
            return self._send(200, fn())
        if table == "admin_users":
            rows = [{"id": 1}]
        elif table == "students":
            email = (query.get("email") or [""])[0].removeprefix("eq.")
            if email:
                rows = [data["mine"]] if email == STUDENT else []
                if "passport_versions" not in select:
                    rows = [{"deleted_at": None}]
            else:
                rows = data["students"]
                offset = int((query.get("offset") or ["0"])[0])
                limit = int((query.get("limit") or ["1000"])[0])
                total = len(rows)
                if "passport_versions" in select or "email" in select:
                    rows = rows[offset : offset + limit]
                else:
                    rows = rows[:1]
                if "count=exact" in (self.headers.get("Prefer") or ""):
                    headers["Content-Range"] = f"{offset}-{offset + len(rows) - 1}/{total}"
        elif table == "passport_versions":
            rows = data["pending"]
            if "count=exact" in (self.headers.get("Prefer") or ""):
                headers["Content-Range"] = f"0-0/{len(rows)}"
        elif table == "sync_runs":
            rows = data["runs"][: int((query.get("limit") or ["50"])[0])]
        elif table == "flags":
            rows = []
            if "count=exact" in (self.headers.get("Prefer") or ""):
                headers["Content-Range"] = "*/0"
        return self._send(200, rows, headers)


def free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--students", type=int, default=250)
    parser.add_argument("--rtt-ms", type=float, default=60.0)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    stats = pp.Stats()
    mock = pp.Mock(pp.Model(), stats, 0.0, 1e12)
    mock.RequestHandlerClass = ApiHandler
    runs = [
        {
            "id": f"00000000-0000-0000-0000-{i:012d}",
            "status": "completed",
            "started_at": "2026-10-31T10:00:00+00:00",
            "finished_at": "2026-10-31T10:00:20+00:00",
            "rows_read": 750,
            "versions_created": 0,
            "error": None,
        }
        for i in range(50)
    ]
    mock.data = {  # type: ignore[attr-defined]
        "students": make_students(args.students),
        "mine": my_student(),
        "pending": [
            {
                "id": f"00000000-0000-0000-0001-{i:012d}",
                "version_number": 1,
                "holder_name": "X",
                "anchor_status": "pending",
                "tx_hash": None,
                "issued_at": "2026-10-31T10:00:00+00:00",
                "anchor_attempts": 0,
                "anchor_last_error": None,
                "anchor_submitted_at": None,
                "anchor_next_attempt_at": None,
                "anchor_status_": "",
                "students": {"passport_id": f"BTU-{i:010d}"},
            }
            for i in range(3)
        ],
        "runs": runs,
    }

    def stats_fn():
        return {  # noqa: E731
            "total_students": args.students,
            "admin_managed_students": args.students // 10,
            "pending_anchors": 3,
            "failed_anchors": 0,
            "open_flags": 0,
            "recent_runs": runs[:5],
        }

    mock.rpcs = {  # type: ignore[attr-defined]
        "sync_inconsistencies": lambda: [],
        "admin_dashboard_stats": stats_fn,
        "admin_health_snapshot": lambda: {
            "last_finished_run": runs[0],
            "last_success_run": runs[0],
            "open_versions": mock.data["pending"],  # type: ignore[attr-defined]
            "inconsistencies": 0,
        },
    }
    threading.Thread(target=mock.serve_forever, daemon=True).start()
    settings.supabase_url = f"http://127.0.0.1:{mock.server_address[1]}"
    settings.supabase_service_role_key = "service-key"
    settings.cors_origins = ["http://localhost:3000"]
    from passport_api import db as db_mod

    getattr(db_mod, "reset_client", lambda: None)()
    # Skip the cryptographic part of the JWT: the email comes from the Authorization header.
    auth_mod._verified_email = lambda token: token  # type: ignore[assignment]

    from passport_api.main import app

    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    mock.rtt = args.rtt_ms / 1000

    def page(requests_: list[tuple[str, str]], token: str) -> tuple[float, int, int]:
        """Issue the requests in parallel (like a browser) with a fresh keep-alive client."""
        stats.reset()
        started = time.perf_counter()
        sizes = 0
        with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}) as client:
            with ThreadPoolExecutor(max_workers=len(requests_)) as pool:
                responses = list(pool.map(lambda r: client.request(r[0], r[1]), requests_))
        for resp in responses:
            assert resp.status_code == 200, (resp.request.url, resp.status_code, resp.text[:200])
            sizes += len(resp.content)
        return time.perf_counter() - started, stats.requests, sizes

    def series(
        name: str, steps: list[list[tuple[str, str]]], token: str, cold: bool = True
    ) -> None:
        # steps run one after another; the requests inside a step run in parallel
        times, dbs, sizes = [], 0, 0
        try:
            from passport_api.cache import clear_all_caches
        except ImportError:  # the old code has no caches
            clear_all_caches = lambda: None  # noqa: E731
        for _ in range(args.runs):
            if cold:
                clear_all_caches()
            total, db_total, size = 0.0, 0, 0
            for step in steps:
                t, d, s = page(step, token)
                total += t
                db_total += d
                size += s
            times.append(total)
            dbs, sizes = db_total, size
            time.sleep(0.2)
        print(
            f"{name}: median {statistics.median(times) * 1000:.0f} ms "
            f"(min {min(times) * 1000:.0f}, max {max(times) * 1000:.0f}) | "
            f"db requests {dbs} | response bytes {sizes}"
        )

    get = lambda p: ("GET", p)  # noqa: E731
    print(f"students={args.students} db rtt={args.rtt_ms} ms, {args.runs} runs each")
    # a warm-up so imports and the first connection do not count
    page([get("/admin/me")], ADMIN)
    dash_old = [
        get("/admin/students?limit=100"),
        get("/admin/versions/pending"),
        get("/admin/sync-runs?limit=5"),
        get("/admin/flags?status=open"),
        get("/admin/health"),
    ]
    dash_new = [get("/admin/stats"), get("/admin/health")]
    has_stats = "/admin/stats" in app.openapi()["paths"]
    if has_stats:
        series(
            "admin dashboard: /admin/me, then /admin/stats + /admin/health",
            [[get("/admin/me")], dash_new],
            ADMIN,
        )
        series("GET /admin/stats alone", [[get("/admin/stats")]], ADMIN)
        series(
            "admin dashboard again within 10 s (cached)",
            [[get("/admin/me")], dash_new],
            ADMIN,
            cold=False,
        )
    # The five requests the dashboard made before /admin/stats existed.
    series(
        "admin dashboard, the old five requests",
        [[get("/admin/me")], dash_old],
        ADMIN,
    )
    series("GET /admin/health alone", [[get("/admin/health")]], ADMIN)
    series(
        "passport page (/me/passport then /me/flags)",
        [[get("/me/passport")], [get("/me/flags")]],
        STUDENT,
    )
    series("passport page, both at once", [[get("/me/passport"), get("/me/flags")]], STUDENT)
    server.should_exit = True
    mock.shutdown()
    _ = json


if __name__ == "__main__":
    main()
