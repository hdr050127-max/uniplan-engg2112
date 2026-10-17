"""Local web adapter for input, on-demand timetable lookup and ranking."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlsplit

from .auto_fetch import AutoFetcher
from .catalog import SnapshotCatalog, load_unit_catalog, suggest_units
from .main import main as run_pipeline
from .profile import normalize_student_input
from .store import ProfileStore
from .preference import pool_spread
from .study import StudyError, StudyRegistry
from timetable_scraper import SYDNEY


ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY = 32768


class AppServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], root: Path = ROOT,
                 *, allow_robots_disallowed: bool = False):
        super().__init__(address, AppHandler)
        self.unit_catalog = load_unit_catalog(
            root / "data/catalog/units_2026_csp.csv",
            (root / "data/catalog/units_2026_cusp.csv",),
        )
        self.snapshot_catalog = SnapshotCatalog(root / "data/processed", root / "data/requirements")
        self.store = ProfileStore(root / "data/private/profiles.sqlite3")
        self.fetcher = AutoFetcher(root, allow_robots_disallowed=allow_robots_disallowed)
        self.fetch_lock = Lock()
        self.studies = StudyRegistry()


def snapshot_age_days(snapshot_time: str | None) -> int | None:
    try:
        stamp = datetime.fromisoformat(snapshot_time or "")
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None
    return max(0, (datetime.now(SYDNEY) - stamp).days)


MAX_MENU = 12
AXES = ("gap", "campus_days", "outside_hours")


def _shortlist_choice(request: dict) -> dict | None:
    """Validate a shortlist choice: the menu's raw G/D/O rows and the chosen index.

    These menus are the training data for the pooled choice model.
    """
    menu, chosen, axes = request.get("menu"), request.get("chosen"), request.get("axes")
    if (not isinstance(menu, list) or not 1 <= len(menu) <= MAX_MENU or
            not isinstance(chosen, int) or isinstance(chosen, bool) or
            not 0 <= chosen < len(menu) or not isinstance(axes, list) or
            not axes or len(set(axes)) != len(axes) or any(axis not in AXES for axis in axes)):
        return None
    for row in menu:
        if (not isinstance(row, list) or len(row) != 3 or
                any(isinstance(value, bool) or not isinstance(value, (int, float)) or
                    not 0 <= value <= 10_000 for value in row)):
            return None
    return {"menu": menu, "chosen": chosen, "axes": axes}


def _optional_ms(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 86_400_000:
        return value
    return None


class AppHandler(BaseHTTPRequestHandler):
    server: AppServer

    def log_message(self, format: str, *args: object) -> None:
        # Request paths can contain a withdrawal code; do not log them.
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: object) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _allowed_host(self) -> bool:
        port = self.server.server_address[1]
        return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _allowed_origin(self) -> bool:
        origin = self.headers.get("Origin")
        port = self.server.server_address[1]
        return origin is None or origin in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    def do_GET(self) -> None:
        if not self._allowed_host():
            self._json(403, {"error": "Invalid host"})
            return
        parts = urlsplit(self.path)
        if parts.path == "/api/catalog":
            self._json(200, {
                "unit_catalog": {"year": 2026, "count": len(self.server.unit_catalog),
                                 "scope": "2026 CSP units plus CUSP All Units supplement; completeness is not guaranteed"},
                "snapshots": self.server.snapshot_catalog.public_snapshots(),
            })
        elif parts.path == "/api/suggest":
            query = parse_qs(parts.query).get("q", [""])[0][:80]
            year_text = parse_qs(parts.query).get("year", [""])[0]
            session = parse_qs(parts.query).get("session_code", [""])[0].upper()
            try:
                year = int(year_text)
            except ValueError:
                year = 0
            available = self.server.snapshot_catalog.available_codes(year, session)
            self._json(200, {"suggestions": suggest_units(query, self.server.unit_catalog, available)})
        else:
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8"),
                     "/favicon.svg": ("favicon.svg", "image/svg+xml")}
            if parts.path not in files:
                self._json(404, {"error": "Not found"})
                return
            name, content_type = files[parts.path]
            self._send(200, (STATIC / name).read_bytes(), content_type)

    def _read_json(self) -> dict | None:
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            self._json(415, {"error": "JSON required"})
            return None
        try:
            size = int(self.headers.get("Content-Length", ""))
            if not 0 < size <= MAX_BODY:
                raise ValueError("Invalid body size")
            request = json.loads(self.rfile.read(size))
            if not isinstance(request, dict):
                raise ValueError("Invalid request")
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"error": "Invalid JSON request"})
            return None
        return request

    def do_POST(self) -> None:
        if not self._allowed_host() or not self._allowed_origin():
            self._json(403, {"error": "Request origin not allowed"})
            return
        routes = {"/api/prepare": self._prepare, "/api/study": self._study,
                  "/api/accept": self._accept}
        handler = routes.get(urlsplit(self.path).path)
        if handler is None:
            self._json(404, {"error": "Not found"})
            return
        request = self._read_json()
        if request is not None:
            handler(request)

    def _prepare(self, request: dict) -> None:
        try:
            if not isinstance(request.get("save", False), bool):
                raise ValueError("Invalid request")
            raw_profile = request.get("profile")
            normalized, errors = normalize_student_input(raw_profile)
            if errors:
                result = run_pipeline(raw_profile, self.server.snapshot_catalog)
            else:
                # Serialize fetch and catalogue refresh for simultaneous submits.
                with self.server.fetch_lock:
                    fetch_result = self.server.fetcher.ensure(
                        normalized, self.server.snapshot_catalog,
                    )
                    result = run_pipeline(
                        raw_profile, self.server.snapshot_catalog,
                        consent_to_save=request.get("save", False), store=self.server.store,
                        selected_groups=request.get("required_groups"),
                        study_registry=self.server.studies,
                        participant=request.get("participant") if isinstance(request.get("participant"), str) else None,
                        pins=request.get("pinned"),
                        excluded=request.get("excluded"),
                    )
                result["fetch"] = fetch_result
                data = result.get("module_two_result")
                if data:
                    age = snapshot_age_days(data.get("snapshot_time"))
                    data["snapshot_age_days"] = age
                if fetch_result["status"] in {"blocked", "failed", "stale_cache"}:
                    if data:
                        # Old local data still supports a clearly marked trial plan.
                        result["warnings"].insert(0, {
                            "code": "stale_snapshot",
                            "message": f"{fetch_result['message']} 当前结果基于 "
                                       f"{data.get('snapshot_time') or '未知时间'} 的本地快照"
                                       f"{f'（约 {age} 天前）' if age is not None else ''}，"
                                       "仅供试算；座位、班级和时间可能已变化。",
                        })
                    else:
                        result["blockers"].insert(0, {
                            "code": "auto_fetch_" + fetch_result["status"],
                            "message": fetch_result["message"],
                        })
        except ValueError:
            self._json(400, {"error": "Invalid JSON request"})
            return
        except (OSError, sqlite3.Error):
            self._json(500, {"error": "无法保存档案，请稍后重试。"})
            return
        self._json(422 if result["status"] == "invalid" else 200, result)

    def _study(self, request: dict) -> None:
        study_id = request.get("study_id")
        if not isinstance(study_id, str):
            self._json(400, {"error": "Invalid study"})
            return
        try:
            session, result = self.server.studies.submit(study_id, request.get("answers"))
        except StudyError as exc:
            self._json(422, {"error": str(exc)})
            return
        result["saved"] = False
        profile_id = session.profile["profile_id"]
        if session.consented:
            try:
                if self.server.store.has_profile(profile_id):
                    self.server.store.save_choices(
                        profile_id, session.study_id, session.design.seed,
                        session.profile["weights"], StudyRegistry.answer_rows(session),
                        list(pool_spread(session.pool)),
                    )
                    self.server.store.record_outcome(profile_id, "study_completed", {
                        "study_id": session.study_id, "status": result["status"],
                        "complete_design": session.design.complete,
                    }, _optional_ms(request.get("elapsed_ms")))
                    result["saved"] = True
            except (OSError, sqlite3.Error):
                self._json(500, {"error": "无法保存比较结果，请稍后重试。"})
                return
        self._json(200, result)

    def _accept(self, request: dict) -> None:
        profile_id, method = request.get("profile_id"), request.get("method")
        rank = request.get("rank")
        detail = _shortlist_choice(request) if method == "shortlist" else {}
        if (not isinstance(profile_id, str) or
                method not in {"learned", "baseline", "equal", "shortlist"} or
                not isinstance(rank, int) or isinstance(rank, bool) or
                not 1 <= rank <= (MAX_MENU if method == "shortlist" else 3) or
                not isinstance(request.get("candidate_id"), str) or detail is None):
            self._json(400, {"error": "Invalid acceptance"})
            return
        try:
            recorded = self.server.store.record_outcome(profile_id, "accepted", {
                "method": method, "rank": rank, "candidate_id": request["candidate_id"][:32],
                **detail,
            }, _optional_ms(request.get("elapsed_ms")))
        except (OSError, sqlite3.Error):
            self._json(500, {"error": "无法记录选择，请稍后重试。"})
            return
        self._json(200, {"recorded": recorded})

    def do_DELETE(self) -> None:
        if not self._allowed_host() or not self._allowed_origin():
            self._json(403, {"error": "Request origin not allowed"})
            return
        path = urlsplit(self.path).path
        prefix = "/api/profiles/"
        if not path.startswith(prefix):
            self._json(404, {"error": "Not found"})
            return
        removed = self.server.store.withdraw(path[len(prefix):])
        self._json(200, {"removed": removed})


def serve(port: int = 8766, *, allow_robots_disallowed: bool = False) -> None:
    with AppServer(("127.0.0.1", port),
                   allow_robots_disallowed=allow_robots_disallowed) as server:
        print(f"UniPlan: http://127.0.0.1:{server.server_address[1]}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
